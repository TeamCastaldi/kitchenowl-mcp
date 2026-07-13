import asyncio

from kitchenowl_mcp import state
from kitchenowl_mcp.tools import recipes


class FakeKitchenOwlClient:
    def __init__(self, recipe: dict) -> None:
        self._recipe = recipe
        self.update_payload: dict | None = None

    async def get_recipe(self, recipe_id: int) -> dict:
        return self._recipe

    async def update_recipe(self, recipe_id: int, payload: dict) -> dict:
        self.update_payload = payload
        return {**self._recipe, **payload}

    async def create_recipe(self, payload: dict) -> dict:
        return payload

    async def list_items(self) -> list[dict]:
        return []

    async def create_item(self, payload: dict) -> dict:
        return payload


def _make_fake_client() -> FakeKitchenOwlClient:
    return FakeKitchenOwlClient(
        recipe={
            "id": 1,
            "name": "Omelet",
            "description": "Original notes.\n\n## Steps\n1. Old step one.\n2. Old step two.",
        }
    )


def test_update_steps_only_preserves_existing_description() -> None:
    client = _make_fake_client()
    state._client = client
    try:
        asyncio.run(recipes.update_recipe(1, steps=["New step."]))
    finally:
        state._client = None

    assert (
        client.update_payload["description"]
        == "Original notes.\n\n## Steps\n1. New step."
    )


def test_update_description_only_preserves_existing_steps() -> None:
    client = _make_fake_client()
    state._client = client
    try:
        asyncio.run(recipes.update_recipe(1, description="New notes."))
    finally:
        state._client = None

    assert (
        client.update_payload["description"]
        == "New notes.\n\n## Steps\n1. Old step one.\n2. Old step two."
    )
