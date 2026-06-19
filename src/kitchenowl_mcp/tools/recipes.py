from .. import state


async def search_recipes(
    query: str = "",
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search KitchenOwl recipes by name or keyword.

    Returns a list of matching recipes with id, name, description, and tags.
    Use get_recipe() with the returned id to fetch full details including
    ingredients and steps. Pass tags to filter by tag name (client-side filter).
    """
    client = state.get_client()
    recipes = await client.list_recipes(search=query, limit=limit)
    if tags:
        tags_lower = {t.lower() for t in tags}
        recipes = [
            r
            for r in recipes
            if any(t.get("name", "").lower() in tags_lower for t in r.get("tags", []))
        ]
    return recipes[:limit]


async def get_recipe(recipe_id: int) -> dict:
    """Get full recipe details including ingredients, steps, and metadata.

    Use search_recipes() first to find the recipe_id.
    """
    return await state.get_client().get_recipe(recipe_id)


async def create_recipe(
    name: str,
    description: str = "",
    ingredients: list[str] | None = None,
    steps: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Create a new recipe in KitchenOwl.

    Each ingredient is a name string (e.g. ["eggs", "butter", "sugar"]).
    The tool looks up each name in the household item catalog and creates a
    new catalog entry if none matches. Steps are plain text strings in order.
    Tags are tag name strings. Returns the created recipe including its new id.
    """
    client = state.get_client()

    items = [
        {
            "name": ingredient.strip(),
            "description": "",
            "optional": False,
            "ordering": idx,
        }
        for idx, ingredient in enumerate(ingredients or [])
    ]

    payload: dict = {
        "name": name,
        "description": description,
        "items": items,
        "steps": [{"text": s} for s in (steps or [])],
        "tags": [{"name": t} for t in (tags or [])],
    }
    return await client.create_recipe(payload)


async def delete_recipe(recipe_id: int) -> dict:
    """Delete a recipe by ID.

    Returns confirmation with the deleted recipe_id.
    Use search_recipes() to find the recipe_id first.
    """
    await state.get_client().delete_recipe(recipe_id)
    return {"deleted_recipe_id": recipe_id}
