# mealie-mcp: chat UI carryover plan

Forward-looking notes for whichever Claude Code session builds the new
`mealie-mcp` server (see `scripts/migrate_ko_to_mealie.py` for the KitchenOwl
-> Mealie data migration this repo already ran). This doc lives here only
because that repo doesn't exist yet — copy it into `mealie-mcp/docs/plans/`
as soon as it does, and delete it from here.

## Why this doc exists

kitchenowl-mcp shipped an embedded browser chat UI (`ENABLE_CHAT_UI`, see
`CLAUDE.md`'s Decision log) that worked well enough to be worth repeating,
not reinventing. This is a record of which parts to carry over deliberately
and which parts are still open decisions, so a fresh session doesn't have to
re-derive either from scratch.

## Patterns to carry over as-is

These were deliberate decisions in kitchenowl-mcp, not defaults — repeat
them rather than re-deciding:

- **A manual tool-calling loop, not the Anthropic SDK's built-in tool
  runner** (`chat/agent.py`). The runner can't pause mid-turn, return an
  HTTP response, and resume from a separate request once a human confirms a
  destructive action. That pause/resume is exactly what the confirmation
  gate below requires.
- **Destructive tools require explicit UI confirmation before executing.**
  For Mealie this means at minimum `delete_recipe`-equivalent and any bulk
  mutation; audit the Mealie tool list for the same "silent data loss" risk
  class that motivated this in kitchenowl-mcp (a prior `update_recipe` bug
  that discarded data on partial update).
- **One `tools/registry.py`-equivalent list, shared by MCP registration and
  the chat agent's tool schema builder**, so the two surfaces can't drift
  apart.
- **Chat agent calls tool functions directly, in-process** — never through
  MCP's own JSON-RPC transport. Going through the protocol for an
  in-process caller adds a serialization hop for no benefit.
- **Two parallel login methods, either sufficient**: shared household
  password + OIDC (Authentik in kitchenowl-mcp's case). Not every household
  member has an IdP account; requiring both is needless friction for a home
  LAN app.
- **An auth-gate middleware that checks the chat path prefix first and
  passes everything else straight through untouched**, and isn't
  constructed at all when the chat feature is disabled. This is the
  isolation guarantee that keeps `/mcp` traffic (claude.ai, and whatever
  other remote-MCP consumer exists by then) completely unaffected by the
  chat feature.
- **Ephemeral, in-memory chat sessions** with a TTL/size-cap eviction policy
  and an explicit reset action ("New chat"). No database dependency for v1.
- **No build step, no frontend framework** for the static chat UI — plain
  HTML/CSS/JS, a hand-rolled markdown-to-HTML pass for assistant replies,
  input HTML-escaped first so tool-result content can't inject markup.

## Open decision: chef personality

The chat agent's system prompt should give the assistant a cooking-forward
persona — candidates are **Julia Child** or **Alton Brown**. Not decided
yet, and doesn't need to be decided now:

- Whether it's a single fixed persona baked into the system prompt, a
  build-time/env-var choice, or a runtime setting the household can switch
  per-session (e.g. a dropdown in the chat header next to "New chat").
- Whether "personality" means voice/tone only, or also shapes behavior
  (e.g. Alton Brown's format-forward, technique-and-equipment explanations
  vs. Julia Child's warmer, more encouraging tone with less digression into
  food science).
- If it becomes user-selectable, where that preference lives — session
  state (resets on "New chat"), a household-level setting, or per-user if
  per-user auth ever lands.

Whoever picks this up: this only needs a paragraph or two added to the
system prompt construction in `chat/agent.py`'s equivalent — don't
over-engineer a persona framework before there's a second persona actually
being built.

## Not yet decided / explicitly out of scope for this note

- Whether mealie-mcp forks `rldiao/mealie-mcp-server` (see prior
  conversation) or is built fresh using the patterns above as the intended
  architecture regardless of which starting point is chosen.
- Mealie's own tools/foods/units facets need a `get_or_create`-with-
  pre-created-id pattern (confirmed empirically during the KO migration,
  see `scripts/migrate_ko_to_mealie.py`) — different from tags/categories,
  which accept inline creation. Any Mealie API client code should account
  for this from the start rather than rediscovering it.
