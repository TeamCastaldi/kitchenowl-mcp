import logging

from .. import state
from ..client import KitchenOwlClient
from ..models import (
    Recipe,
    RecipeItem,
    normalize_tags,
    parse_description,
    serialize_description,
)

logger = logging.getLogger(__name__)


async def resolve_ingredient_items(
    client: KitchenOwlClient, ingredient_names: list[str]
) -> list[RecipeItem]:
    """Resolve ingredient name strings against the household item catalog,
    creating new catalog entries for unmatched names."""
    catalog = await client.list_items() if ingredient_names else []
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
    for ingredient_name in ingredient_names:
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
        items.append(RecipeItem(name=resolved.get("name", ingredient_name.strip())))
    return items


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
    return [_normalize_recipe(r) for r in recipes[:limit]]


async def get_recipe(recipe_id: int) -> dict:
    """Get full recipe details including ingredients, steps, and metadata.

    description contains only free-text notes; steps is a separate ordered
    list. Use search_recipes() first to find the recipe_id.
    """
    raw = await state.get_client().get_recipe(recipe_id)
    return _normalize_recipe(raw)


def _normalize_recipe(raw: dict) -> dict:
    description, steps = parse_description(raw.get("description") or "")
    result = dict(raw)
    result["description"] = description
    result["steps"] = steps
    result["tags"] = normalize_tags(raw.get("tags") or [])
    return result


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
    items = await resolve_ingredient_items(client, ingredients or [])
    recipe = Recipe(
        name=name,
        description=description,
        steps=steps or [],
        items=items,
        tags=list(tags or []),
    )
    return await client.create_recipe(recipe.to_wire_payload())


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
    description and steps update independently without clobbering each
    other — pass steps=[] to clear steps while keeping description, or
    description="" to clear description while keeping steps.
    Tags replace the full existing tag set (pass [] to clear all tags).
    Use search_recipes() to find the recipe_id.
    """
    client = state.get_client()
    payload: dict = {}

    if name is not None:
        payload["name"] = name

    if description is not None or steps is not None:
        if description is None or steps is None:
            current = await client.get_recipe(recipe_id)
            current_description, current_steps = parse_description(
                current.get("description") or ""
            )
        free_text = description if description is not None else current_description
        step_list = steps if steps is not None else current_steps
        payload["description"] = serialize_description(free_text, step_list)

    if tags is not None:
        payload["tags"] = list(tags)

    if ingredients is not None:
        items = await resolve_ingredient_items(client, ingredients)
        payload["items"] = [i.model_dump() for i in items]

    return await client.update_recipe(recipe_id, payload)


async def list_tags() -> list[dict]:
    """List all recipe tags defined in this KitchenOwl household.

    Returns a list of tag objects with id and name.
    Use the name strings with search_recipes(tags=[...]) or create_recipe(tags=[...]).
    """
    return await state.get_client().list_tags()


async def mark_recipe_made(recipe_id: int) -> dict:
    """Record that a recipe was just cooked.

    Increments the cook count and logs the timestamp in KitchenOwl's
    cooking history. Use search_recipes() to find the recipe_id.
    Returns the updated recipe.
    """
    return await state.get_client().cook_recipe(recipe_id)


async def delete_recipe(recipe_id: int) -> dict:
    """Delete a recipe by ID.

    Returns confirmation with the deleted recipe_id.
    Use search_recipes() to find the recipe_id first.
    """
    await state.get_client().delete_recipe(recipe_id)
    return {"deleted_recipe_id": recipe_id}
