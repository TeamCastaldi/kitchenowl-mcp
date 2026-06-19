"""Verify the package structure is importable without env vars."""


def test_package_imports() -> None:
    from kitchenowl_mcp import auth, client, state  # noqa: F401
    from kitchenowl_mcp.tools import meal_plan, recipes, shopping  # noqa: F401


def test_get_client_raises_before_init() -> None:
    from kitchenowl_mcp import state

    state._client = None
    try:
        state.get_client()
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as e:
        assert "not initialized" in str(e)
