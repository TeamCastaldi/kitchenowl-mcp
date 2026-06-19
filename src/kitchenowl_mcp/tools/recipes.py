import logging

from .. import state

logger = logging.getLogger(__name__)


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

    catalog = await client.list_items() if ingredients else []
    catalog_by_key: dict[str, dict] = {
        key: item
        for item in catalog
        for key in (
            (item.get("name") or "").lower(),
            (item.get("default_key") or "").lower(),
        )
        if key
    }

    items = []
    for ingredient_name in ingredients or []:
        lookup_key = ingredient_name.lower().strip()
        existing = catalog_by_key.get(lookup_key)
        if existing:
            resolved = existing
        else:
            logger.warning(
                "Ingredient %r not found in catalog; creating new item", ingredient_name
            )
            resolved = await client.create_item(
                {
                    "name": ingredient_name.strip(),
                    "default_key": lookup_key.replace(" ", "_"),
                }
            )
        items.append(
            {
                "name": resolved.get("name", ingredient_name.strip()),
                "description": "",
                "optional": False,
            }
        )

    steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps or []))
    full_description = "\n\n".join(filter(None, [description, steps_text]))

    payload: dict = {
        "name": name,
        "description": full_description,
        "items": items,
        "tags": list(tags or []),
    }
    return await client.create_recipe(payload)


async def update_recipe(
    recipe_id: int,
    name: str | None = None,
    description: str | None = None,
    ingredients: list[str] | None = None,
    steps: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Update fields of an existing recipe in KitchenOwl.

    Only provided fields are changed; omitted fields are left as-is.
    Steps are formatted as a numbered list and appended to description.
    Tags replace the full existing tag set (pass [] to clear all tags).
    Use search_recipes() to find the recipe_id.
    """
    client = state.get_client()
    payload: dict = {}

    if name is not None:
        payload["name"] = name

    if description is not None or steps is not None:
        steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps or []))
        full_description = "\n\n".join(filter(None, [description or "", steps_text]))
        payload["description"] = full_description

    if tags is not None:
        payload["tags"] = list(tags)

    if ingredients is not None:
        catalog = await client.list_items()
        catalog_by_key: dict[str, dict] = {
            key: item
            for item in catalog
            for key in (
                (item.get("name") or "").lower(),
                (item.get("default_key") or "").lower(),
            )
            if key
        }
        items = []
        for ingredient_name in ingredients:
            lookup_key = ingredient_name.lower().strip()
            existing = catalog_by_key.get(lookup_key)
            if existing:
                resolved = existing
            else:
                logger.warning(
                    "Ingredient %r not found in catalog; creating new item",
                    ingredient_name,
                )
                resolved = await client.create_item(
                    {
                        "name": ingredient_name.strip(),
                        "default_key": lookup_key.replace(" ", "_"),
                    }
                )
            items.append(
                {
                    "name": resolved.get("name", ingredient_name.strip()),
                    "description": "",
                    "optional": False,
                }
            )
        payload["items"] = items

    return await client.update_recipe(recipe_id, payload)


async def delete_recipe(recipe_id: int) -> dict:
    """Delete a recipe by ID.

    Returns confirmation with the deleted recipe_id.
    Use search_recipes() to find the recipe_id first.
    """
    await state.get_client().delete_recipe(recipe_id)
    return {"deleted_recipe_id": recipe_id}
