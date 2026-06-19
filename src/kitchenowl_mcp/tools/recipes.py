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
    ingredients: list[dict] | None = None,
    steps: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Create a new recipe in KitchenOwl.

    Each ingredient dict should include: name (required), amount (optional float
    as string), unit (optional string), note (optional string).
    Steps are plain text strings in order. Tags are tag name strings.
    Returns the created recipe including its new id.
    """
    payload: dict = {
        "name": name,
        "description": description,
        "items": [
            {
                "name": ing.get("name", ""),
                "amount": ing.get("amount", ""),
                "unit": ing.get("unit", ""),
                "description": ing.get("note", ""),
            }
            for ing in (ingredients or [])
        ],
        "steps": [{"text": s} for s in (steps or [])],
        "tags": [{"name": t} for t in (tags or [])],
    }
    return await state.get_client().create_recipe(payload)
