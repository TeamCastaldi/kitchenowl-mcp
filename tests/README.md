# Tests

pytest test suite. All automated tests live here.

## Structure

```
tests/
    conftest.py         Shared fixtures and pytest configuration
    test_imports.py     Import validation — confirms modules load without env vars
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
