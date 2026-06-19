from .. import state
from ..config import get_settings


async def get_shopping_list() -> list[dict]:
    """Return all current items on the household shopping list.

    Items include name, amount, unit, and whether they are checked off.
    """
    settings = get_settings()
    return await state.get_client().get_shopping_list_items(
        settings.kitchenowl_default_list_id
    )


async def add_shopping_list_items(items: list[dict]) -> dict:
    """Add one or more items to the household shopping list.

    Each item dict should include: name (required), amount (optional string),
    unit (optional string). Example: [{"name": "milk", "amount": "2", "unit": "L"}]
    Returns a summary of added items.
    """
    settings = get_settings()
    client = state.get_client()
    list_id = settings.kitchenowl_default_list_id
    results = []
    for item in items:
        payload = {
            "name": item.get("name", ""),
            "amount": str(item.get("amount", "")),
            "unit": item.get("unit", ""),
        }
        result = await client.add_shopping_item(list_id, payload)
        results.append(result)
    return {"added": len(results), "items": results}


async def clear_checked_items() -> dict:
    """Remove all checked-off items from the household shopping list.

    Returns the count of items removed.
    """
    settings = get_settings()
    client = state.get_client()
    list_id = settings.kitchenowl_default_list_id
    items = await client.get_shopping_list_items(list_id)
    checked = [i for i in items if i.get("checked", False)]
    for item in checked:
        await client.remove_shopping_item(list_id, item["id"])
    return {"removed": len(checked)}
