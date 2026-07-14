# Tests

pytest test suite. All automated tests live here.

## Structure

```
tests/
    conftest.py            Shared fixtures and pytest configuration
    test_imports.py        Import validation — confirms modules load without env vars
    test_models.py         Recipe/RecipeItem models, steps-in-description parsing
    test_recipes_tools.py  Recipe tool handlers (update merging, schema audit)
    test_chat_dispatch.py  Chat tool-registry/dispatch drift-detection, schema caching
    test_chat_agent.py     Chat agent tool-calling loop, destructive-tool confirmation gating
    test_chat_sessions.py  Chat session lifecycle — reuse, TTL/size pruning, reset
    test_chat_config.py    Chat settings validation (validate_chat_settings)
    test_chat_http.py      Chat HTTP routes/middleware via Starlette TestClient,
                            including the /mcp-is-never-gated isolation guarantee
```

## Running tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v
```

## Conventions

- Test files are named `test_{module}.py`
- Test functions are named `test_{what_it_does}`
- Use fixtures in `conftest.py` for shared setup
- Tests must pass before any PR is merged — CI enforces this
- Import tests pass without a running KitchenOwl instance — they avoid calling `get_settings()` or making any HTTP calls
