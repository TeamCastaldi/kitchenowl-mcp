# Comprehensive Plan: kitchenowl-mcp on Google Cloud for Gemini Enterprise

## Context

kitchenowl-mcp is a FastMCP server (Python 3.11, streamable-http transport) that connects
AI assistants to a household KitchenOwl instance. It currently runs on a home server
(heimdall) behind Traefik and is used by claude.ai. The goal is to also make it available
from Gemini conversations via Google Cloud's "Custom MCP Server" connector in Gemini
Enterprise — a preview feature that lets Gemini agents call tools on external MCP servers.

The repo has been migrated to TeamCastaldi/kitchenowl-mcp. The OAuth prototype from the
previous session was rolled back; this plan covers a clean, end-to-end implementation.

**Existing claude.ai path is never touched.** It continues running on heimdall unchanged.
The Cloud Run deployment is a second, independent instance.

---

## What Gemini Enterprise Requires

| Requirement | Status | Notes |
|---|---|---|
| `streamable-http` transport | ✓ Already implemented | No change needed |
| Publicly reachable HTTPS endpoint | Needs Cloud Run deploy | — |
| OAuth 2.0 inbound auth | Needs code + GCP setup | The main work |
| Gemini Enterprise subscription | ✓ Confirmed | — |
| KitchenOwl reachable via public URL | **Must verify first** | Blocker if missing |

---

## Phase 0 — Prerequisites (manual, before any code)

### 0a. Confirm KitchenOwl's public URL

The Cloud Run container cannot reach `http://kitchenowl-front:80` (internal Docker network).
It needs a public HTTPS endpoint for the KitchenOwl API.

Check heimdall's compose stack for a Traefik label like:
`traefik.http.routers.kitchenowl.rule=Host('kitchenowl.castaldifamily.com')`

- **If it exists** → use that URL as `KITCHENOWL_API_URL` in Cloud Run. Done.
- **If it doesn't exist** → add a Traefik route for the KitchenOwl backend, or use
  Cloudflare Zero Trust Tunnel to expose it privately. The MCP server only calls
  KitchenOwl's REST API, so a read/write API endpoint with Bearer auth is sufficient.

### 0b. Google Cloud project

Enable APIs (one-time, in any GCP project with billing):
```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com
```

### 0c. Google OAuth 2.0 app

In Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID:
- Application type: **Web application**
- Name: `kitchenowl-mcp`
- Authorized redirect URIs: add `https://<cloud-run-url>/oauth/callback`
  (placeholder — update after Phase 2 deploy)

Save the `client_id` (ends in `.apps.googleusercontent.com`) and `client_secret`.

---

## Phase 1 — Application Code Changes

**Target files:** `src/kitchenowl_mcp/config.py`, `src/kitchenowl_mcp/server.py`, `.env.example`

No new files needed. FastMCP 3.x (installed version: 3.4.2) has a built-in
`GoogleProvider` at `fastmcp.server.auth.providers.google` that acts as a full
Google OAuth 2.0 proxy — it exposes authorization endpoints, validates tokens via
Google's tokeninfo API (using httpx, already a dep), and issues FastMCP session tokens.
No `google-auth` library needed.

### 1a. `pyproject.toml` — pin FastMCP ≥ 3.x

The existing constraint `fastmcp>=2.0.0` will resolve to 3.4.2+ correctly. No change
required unless pinning is desired for reproducibility:
```toml
"fastmcp>=3.4.0",
```

### 1b. `src/kitchenowl_mcp/config.py` — add OAuth fields

Add four optional settings after `mcp_port`. All default to off/empty so the heimdall
deployment is unaffected:

```python
# OAuth (required for Gemini Enterprise / Cloud Run deployment)
require_oauth: bool = False
oauth_client_id: str = ""
oauth_client_secret: str = ""
oauth_base_url: str = ""   # The Cloud Run service URL, e.g. https://kitchenowl-mcp-xxxx.run.app
```

### 1c. `src/kitchenowl_mcp/server.py` — refactor to `_build_server()`

The existing module-level `mcp = FastMCP(...)` pattern cannot accept auth at import time
(violates the lazy-settings constraint). Refactor: move `FastMCP(...)` + all `add_tool()`
calls into a `_build_server()` factory called only from `main()`.

```python
def _build_server() -> FastMCP:
    settings = get_settings()
    auth = None
    if settings.require_oauth:
        from fastmcp.server.auth.providers.google import GoogleProvider
        if not settings.oauth_client_id or not settings.oauth_base_url:
            raise ValueError(
                "OAUTH_CLIENT_ID and OAUTH_BASE_URL are required when REQUIRE_OAUTH=true"
            )
        auth = GoogleProvider(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret or None,
            base_url=settings.oauth_base_url,
        )
        logger.info("OAuth enabled via GoogleProvider (base=%s)", settings.oauth_base_url)

    server = FastMCP("KitchenOwl", lifespan=lifespan, auth=auth)
    server.add_tool(recipes.search_recipes)
    server.add_tool(recipes.get_recipe)
    server.add_tool(recipes.create_recipe)
    server.add_tool(recipes.update_recipe)
    server.add_tool(recipes.delete_recipe)
    server.add_tool(recipes.list_tags)
    server.add_tool(recipes.mark_recipe_made)
    server.add_tool(shopping.get_shopping_list)
    server.add_tool(shopping.add_shopping_list_items)
    server.add_tool(shopping.clear_checked_items)
    server.add_tool(meal_plan.get_meal_plan)
    server.add_tool(meal_plan.add_meal_plan_entry)
    return server


def main() -> None:
    settings = get_settings()
    server = _build_server()
    server.run(transport="streamable-http", host="0.0.0.0", port=settings.mcp_port)
```

Tests don't import `server.py` (by design — see `tests/test_imports.py`), so removing
the module-level `mcp` reference breaks nothing.

### 1d. `.env.example` — document new vars

Append (commented out, since they're off by default):
```bash
# OAuth — required for Gemini Enterprise / Cloud Run deployment
# REQUIRE_OAUTH=true
# OAUTH_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
# OAUTH_CLIENT_SECRET=GOCSPX-your-secret
# OAUTH_BASE_URL=https://kitchenowl-mcp-xxxx.run.app
```

---

## Phase 2 — Cloud Run Deployment

### 2a. Artifact Registry

```bash
gcloud artifacts repositories create kitchenowl-mcp \
  --repository-format=docker \
  --location=us-central1
```

### 2b. Store the KitchenOwl API token in Secret Manager

```bash
echo -n "your-kitchenowl-token" | \
  gcloud secrets create kitchenowl-api-token --data-file=-
```

### 2c. Build and push image

The existing `Dockerfile` works without changes. Use Cloud Build to avoid needing
Docker locally:
```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/PROJECT_ID/kitchenowl-mcp/app:latest
```

### 2d. First deploy (without OAuth, to get the URL)

Deploy without `REQUIRE_OAUTH` first so we can note the `*.run.app` URL for the
OAuth redirect URI:
```bash
gcloud run deploy kitchenowl-mcp-gemini \
  --image us-central1-docker.pkg.dev/PROJECT_ID/kitchenowl-mcp/app:latest \
  --region us-central1 \
  --port 8000 \
  --set-env-vars "KITCHENOWL_API_URL=https://kitchenowl.castaldifamily.com" \
  --set-env-vars "KITCHENOWL_HOUSEHOLD_ID=1,KITCHENOWL_DEFAULT_LIST_ID=1" \
  --set-secrets "KITCHENOWL_API_TOKEN=kitchenowl-api-token:latest" \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2
```

Note the assigned URL (e.g. `https://kitchenowl-mcp-gemini-abc123-uc.a.run.app`).

### 2e. Add redirect URI to OAuth app

In GCP Console → OAuth client → add:
`https://kitchenowl-mcp-gemini-abc123-uc.a.run.app/oauth/callback`

### 2f. Redeploy with OAuth enabled

```bash
gcloud run services update kitchenowl-mcp-gemini \
  --region us-central1 \
  --set-env-vars "REQUIRE_OAUTH=true" \
  --set-env-vars "OAUTH_CLIENT_ID=<client_id>" \
  --set-env-vars "OAUTH_CLIENT_SECRET=<client_secret>" \
  --set-env-vars "OAUTH_BASE_URL=https://kitchenowl-mcp-gemini-abc123-uc.a.run.app"
```

Why `--allow-unauthenticated`? Cloud Run's own IAM auth is separate from MCP-layer
OAuth. Gemini Enterprise does not present GCP IAM tokens; it presents OAuth tokens that
our `GoogleProvider` middleware validates. The `--allow-unauthenticated` flag only
controls GCP's network-level IAM gate, not the app-level OAuth check.

---

## Phase 3 — CI/CD via GitHub Actions

Add a second job to `.github/workflows/ci.yml` that deploys to Cloud Run on push to `main`.
Uses Workload Identity Federation (no service account key stored in secrets):

```yaml
deploy-cloud-run:
  needs: lint-and-test
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  permissions:
    contents: read
    id-token: write   # required for WIF

  steps:
    - uses: actions/checkout@v4

    - id: auth
      uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: 'projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github'
        service_account: 'kitchenowl-mcp-deployer@PROJECT_ID.iam.gserviceaccount.com'

    - uses: google-github-actions/setup-gcloud@v2

    - name: Build and push
      run: |
        gcloud builds submit \
          --tag us-central1-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/kitchenowl-mcp/app:${{ github.sha }}

    - name: Deploy
      run: |
        gcloud run deploy kitchenowl-mcp-gemini \
          --image us-central1-docker.pkg.dev/${{ vars.GCP_PROJECT_ID }}/kitchenowl-mcp/app:${{ github.sha }} \
          --region us-central1
```

**Required GitHub repo variables/secrets:**
- `GCP_PROJECT_ID` (repo variable)
- `GCP_PROJECT_NUMBER` (repo variable, for WIF provider path)

**One-time GCP setup for WIF:**
```bash
# Create WIF pool and provider
gcloud iam workload-identity-pools create github \
  --location global --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github \
  --location global \
  --workload-identity-pool github \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository"

# Create deployer service account with required roles
gcloud iam service-accounts create kitchenowl-mcp-deployer

for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding PROJECT_ID \
    --member "serviceAccount:kitchenowl-mcp-deployer@PROJECT_ID.iam.gserviceaccount.com" \
    --role "$role"
done

# Bind the GitHub repo to the service account
gcloud iam service-accounts add-iam-policy-binding \
  kitchenowl-mcp-deployer@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/.../attribute.repository/TeamCastaldi/kitchenowl-mcp"
```

---

## Phase 4 — Gemini Enterprise Connector Registration

This is entirely manual in the Google Cloud Console.

1. Navigate to **Agent Builder → Data Stores → Create**
2. Select **Custom MCP Server (Preview)**
3. Enter the Cloud Run URL: `https://kitchenowl-mcp-gemini-abc123-uc.a.run.app`
4. The connector will call `/.well-known/oauth-authorization-server` to discover auth metadata
   (served automatically by FastMCP's `GoogleProvider`)
5. Enter the OAuth `client_id` and `client_secret` (same values as the Google OAuth app)
6. Click **Enable actions** → enable whichever of the 12 tools Gemini should call
7. **Note:** Every tool call requires user confirmation in Gemini Enterprise by default —
   this is a platform constraint, not configurable per-tool

---

## Phase 5 — CLAUDE.md Update

Update CLAUDE.md to reflect:
- New repo home: `TeamCastaldi/kitchenowl-mcp`
- Cloud Run deployment as second target (alongside heimdall)
- OAuth config vars
- WIF/CI-CD setup status

---

## Files Modified

| File | Change |
|---|---|
| `src/kitchenowl_mcp/config.py` | +4 OAuth settings fields |
| `src/kitchenowl_mcp/server.py` | Refactor to `_build_server()`, conditional `GoogleProvider` |
| `.env.example` | Document new OAuth vars |
| `.github/workflows/ci.yml` | Add `deploy-cloud-run` job |
| `CLAUDE.md` | Update current state, add Cloud Run + OAuth docs |

No new source files. No new Python dependencies.

---

## Verification Sequence

### After Phase 1 (code changes):
```bash
pytest tests/ -v   # must pass (especially test_imports.py — server.py not imported)
ruff check src/ && ruff format --check src/
```

### After Phase 2 (Cloud Run, OAuth disabled):
```bash
curl https://kitchenowl-mcp-gemini-abc123-uc.a.run.app/mcp
# Expect: MCP protocol response (list of tools)
```

### After Phase 2 (OAuth enabled):
```bash
# Without token — must reject
curl -v https://kitchenowl-mcp-gemini-abc123-uc.a.run.app/mcp
# Expect: 401 or redirect to OAuth authorize endpoint

# OAuth discovery — must respond
curl https://kitchenowl-mcp-gemini-abc123-uc.a.run.app/.well-known/oauth-authorization-server
# Expect: JSON with authorization_endpoint, token_endpoint, etc.
```

### End-to-end (Gemini):
In a Gemini conversation: "Using kitchenowl, what recipes do I have?"
Gemini should prompt for confirmation, then call `search_recipes` and return results.

---

## Implementation Order

1. Clone `TeamCastaldi/kitchenowl-mcp` → verify baseline (pre-OAuth)
2. Phase 0: verify KitchenOwl public URL; create GCP OAuth client
3. Phase 1: code changes → commit → CI green
4. Phase 2a–d: Cloud Run deploy (no OAuth) → verify `/mcp` endpoint
5. Phase 2e–f: add redirect URI → redeploy with OAuth → verify 401 + discovery
6. Phase 3: CI/CD GitHub Actions job + WIF setup
7. Phase 4: Gemini Enterprise console registration
8. Phase 5: CLAUDE.md update