#!/usr/bin/env python3
"""One-shot script: delete stub recipes and create Classic Omelet.

Run on heimdall where KITCHENOWL_* env vars are set:
    python scripts/setup_recipes.py
"""

import asyncio
import sys

sys.path.insert(0, "src")

from kitchenowl_mcp.client import KitchenOwlClient
from kitchenowl_mcp.config import get_settings

STUB_IDS = [1, 2, 6]
STUB_NAMES = {
    "omelet test",
    "omelet eggs test",
    "omelet butter test",
    "omelet oil test",
    "ingredient test",
    "tag test",
}

CLASSIC_OMELET = {
    "name": "Classic Omelet",
    "description": "A simple French-style omelet — tender, just set, folded to order.",
    "ingredients": ["eggs", "butter", "salt"],
    "steps": [
        "Crack 3 eggs into a bowl, add a pinch of salt, and beat until fully combined with no streaks.",
        "Heat an 8-inch non-stick skillet over medium-low heat for about 1 minute.",
        "Add 1 tablespoon of butter and swirl to coat the pan as it melts.",
        "Pour in the beaten eggs and let them sit undisturbed for 10–15 seconds until the edges just begin to set.",
        "Using a silicone spatula, gently push the cooked edges toward the center while tilting the pan so the uncooked egg flows to the edges.",
        "When the eggs are mostly set but still slightly glossy on top, remove the pan from the heat.",
        "Tilt the pan at a 45-degree angle and fold the near edge of the omelet to the center, then roll it onto a plate seam-side down.",
        "Serve immediately, optionally garnished with fresh herbs.",
    ],
    "tags": [],
}


async def main() -> None:
    s = get_settings()
    client = KitchenOwlClient(
        base_url=s.kitchenowl_base_url,
        token=s.kitchenowl_api_token.get_secret_value(),
        household_id=s.kitchenowl_household_id,
    )

    # --- delete by known IDs ---
    for rid in STUB_IDS:
        try:
            await client.delete_recipe(rid)
            print(f"deleted recipe id={rid}")
        except Exception as e:
            print(f"skip id={rid}: {e}")

    # --- delete by name ---
    recipes = await client.list_recipes(limit=200)
    for r in recipes:
        if r.get("name", "").lower() in STUB_NAMES:
            try:
                await client.delete_recipe(r["id"])
                print(f"deleted recipe name={r['name']!r} id={r['id']}")
            except Exception as e:
                print(f"skip name={r['name']!r}: {e}")

    # --- create Classic Omelet ---
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
    for ing in CLASSIC_OMELET["ingredients"]:
        lookup = ing.lower().strip()
        resolved = catalog_by_key.get(lookup) or await client.create_item(
            {"name": ing.strip(), "default_key": lookup.replace(" ", "_")}
        )
        items.append(
            {
                "name": resolved.get("name", ing.strip()),
                "description": "",
                "optional": False,
            }
        )

    payload = {
        "name": CLASSIC_OMELET["name"],
        "description": CLASSIC_OMELET["description"],
        "items": items,
        "steps": [{"text": s} for s in CLASSIC_OMELET["steps"]],
        "tags": [],
    }
    result = await client.create_recipe(payload)
    print(f"created recipe id={result.get('id')} name={result.get('name')!r}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
