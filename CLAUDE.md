# CLAUDE.md

This file provides context for Claude (and other LLM assistants) working in this repository.

---

## Project identity

**kitchenowl-mcp** — An MCP (Model Context Protocol) server that connects Claude to a household KitchenOwl instance. Enables read/write access to recipes, shopping lists, and meal plans from within a Claude conversation. Deployed alongside KitchenOwl in a home Docker Compose stack on heimdall, exposed to claude.ai via Traefik.

## Stack

- **Runtime:** Python 3.11+
- **MCP framework:** FastMCP 2.x (streamable-http transport)
- **HTTP client:** httpx (async)
- **Config:** pydantic-settings (reads `KITCHENOWL_*` env vars)
- **Linter/formatter:** ruff
- **Tests:** pytest

## Architecture

```
claude.ai
    │  HTTP/SSE (remote MCP, streamable-http)
    ▼
kitchenowl-mcp  (container on heimdall, port 8000)
    │  HTTP REST + Bearer token
    │  internal Docker network only
    ▼
kitchenowl-back  (existing KitchenOwl container)
```

**Key modules:**
- `src/kitchenowl_mcp/config.py` — `Settings` via pydantic-settings, accessed lazily via `get_settings()`
- `src/kitchenowl_mcp/auth.py` — `get_token(request_context=None)` — the auth seam; swap implementation for per-user lookup in v2 without touching tool handlers
- `src/kitchenowl_mcp/client.py` — `KitchenOwlClient` — ALL KitchenOwl HTTP calls live here; one place to fix when the API changes
- `src/kitchenowl_mcp/state.py` — module-level `_client` singleton; initialized in server lifespan, accessed by tools via `get_client()`
- `src/kitchenowl_mcp/tools/` — one file per domain (recipes, shopping, meal_plan); plain async functions registered in server.py via `mcp.add_tool()`
- `src/kitchenowl_mcp/server.py` — FastMCP app, lifespan hook (health-checks KitchenOwl at startup), tool registration, `main()` entry point

## Constraints (non-negotiable)

- Never commit `.env` or any token/secret — only `.env.example`
- All KitchenOwl HTTP calls MUST go through `KitchenOwlClient` in `client.py` — no direct httpx calls in tool handlers
- `get_token()` is the only place the API token is read — never reference `settings.kitchenowl_api_token` directly in tools
- `get_settings()` is lazy (lru_cache) — do not call at module import time; call inside functions so import tests pass
- Server must fail loudly at startup if KitchenOwl is unreachable (lifespan health check enforces this)
- Conventional Commits format required for all commits

## Code style

- ruff, 88 char line length, double quotes, isort
- No comments unless the WHY is non-obvious
- No module-level settings access (breaks import tests and delays startup error reporting)
- Type hints required on all function signatures

## Current state

### Done

- v1 MCP server with 9 tools: `search_recipes`, `get_recipe`, `create_recipe`, `delete_recipe`, `get_shopping_list`, `add_shopping_list_items`, `clear_checked_items`, `get_meal_plan`, `add_meal_plan_entry`
- `create_recipe` verified working — KitchenOwl recipe item schema accepts only `{name, description, optional}`; `id` and `ordering` are unknown fields and must be omitted
- Dockerfile for container deployment
- Deployed to heimdall Compose stack
- CI: ruff + pytest

### Not started

- P1 tools: `update_recipe`, `list_tags`, `mark_recipe_made`
- Structured logging
- Per-user token mapping (v2, OpenWebUI)

## Open questions

1. Does KitchenOwl's API token expire? Plan assumes permanent (no refresh logic). Verify in KitchenOwl settings before prod deploy.
2. Confirm `KITCHENOWL_DEFAULT_LIST_ID=1` is a valid list ID in the household.
3. Confirm no Authentik middleware on the `kitchenowl-mcp` Traefik router — claude.ai sends its own auth headers and cannot pass Authentik.

## Decision log

- **FastMCP over bare `mcp` library** — higher-level API, built-in streamable-http transport, auto schema generation from type hints
- **`get_token(request_context=None)` signature** — accepts context param as v2 seam for per-user lookup without refactoring tool handlers
- **Module-level `state._client` singleton** — avoids circular imports while giving tools access to the shared httpx client initialized in lifespan
- **`KITCHENOWL_DEFAULT_LIST_ID` env var** — explicit config over auto-discovery; simpler, no extra API call per operation

---

*Last updated: 2026-06-19 | Session: create_recipe debugging + delete_recipe*
