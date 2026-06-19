#!/usr/bin/env python3
"""One-shot script: delete stub recipes, create Classic Omelet, update recipe steps.

Run on heimdall where KITCHENOWL_* env vars are set:
    python scripts/setup_recipes.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kitchenowl_mcp.auth import get_token
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

RECIPE_STEPS = {
    1: {
        "name": "Scrambled Eggs",
        "steps": [
            "Crack eggs into a bowl — not the pan. Fish out any shell with a wet fingertip (shell chases shell).",
            "Add a small splash of oat milk or water and a pinch of salt. Whisk until fully combined — no streaks.",
            "Place a non-stick pan or cast iron over medium-low heat. Add a small pat of butter or Earth Balance.",
            "When the butter melts and foams (not browns), pour in the eggs.",
            "Let sit 10 seconds untouched, then gently push from the edges toward the center with a spatula.",
            "Keep making slow, lazy folds. Don't rush — low heat is the secret.",
            "When the eggs look almost done but still slightly shiny on top, pull the pan off the heat. Residual heat finishes them.",
            "Plate immediately. Scrambled eggs keep cooking even off the stove — don't wait.",
        ],
    },
    2: {
        "name": "Fried Eggs",
        "steps": [
            "Heat a small non-stick pan over medium heat. Add a thin layer of butter or oil.",
            "Crack the egg into a small bowl first, then gently slide it into the pan.",
            "SUNNY SIDE UP: Leave it alone. When the white is fully set (no jiggle, no translucent spots) and edges are slightly crispy, it's done. The yolk stays runny on top.",
            "OVER EASY: Once the white is set, slide a thin spatula fully under the egg and flip in one confident motion. Cook 20–30 more seconds. Yolk should still be runny inside.",
            "Season with salt after plating.",
            "The lesson: confidence with the spatula matters — hesitation breaks yolks. Practice the motion before committing.",
        ],
    },
    3: {
        "name": "Hard Boiled Eggs",
        "steps": [
            "Place eggs in a single layer in a saucepan. Cover with cold water by about an inch.",
            "Bring to a full boil over high heat.",
            "The moment it boils, turn the heat off, put the lid on, and set a timer: 9 minutes for fully set (no green ring), 7 minutes for a slightly jammy yolk.",
            "While the timer runs, fill a bowl with ice water.",
            "When the timer goes off, use a slotted spoon to move eggs straight into the ice water. Leave them at least 5 minutes.",
            "To peel: gently crack on the counter all around, then peel under a thin stream of running water.",
            "The lesson: the ice bath stops cooking immediately — this is why they don't turn gray-green.",
        ],
    },
    4: {
        "name": "Classic Omelet",
        "steps": [
            "Whisk 2 eggs with a splash of water and a pinch of salt until completely uniform — no streaks.",
            "Heat a non-stick pan over medium-high heat. Add butter and swirl to coat the whole pan.",
            "When butter foams, pour in the eggs. Let sit 5 seconds.",
            "Using a spatula, pull the cooked edges toward the center while tilting the pan so uncooked egg flows to the edges. Work all the way around.",
            "When the top is just barely set (still slightly glossy), add any fillings to one half — cheese, herbs, sautéed vegetables, whatever you like.",
            "Fold the unfilled half over the filled half.",
            "Tilt the pan and roll or slide the omelet onto the plate seam-side down.",
            "The lesson: the first omelet is always ugly. That's expected. Focus on the motion, not the result.",
        ],
    },
}


def _steps_to_description(steps: list[str]) -> str:
    return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))


async def main() -> None:
    s = get_settings()
    client = KitchenOwlClient(
        base_url=s.kitchenowl_api_url,
        token=get_token(),
        household_id=s.kitchenowl_household_id,
    )
    try:
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
            if (r.get("name") or "").lower() in STUB_NAMES:
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

        steps_text = _steps_to_description(CLASSIC_OMELET["steps"])
        full_description = "\n\n".join(
            filter(None, [CLASSIC_OMELET["description"], steps_text])
        )
        payload = {
            "name": CLASSIC_OMELET["name"],
            "description": full_description,
            "items": items,
            "tags": [],
        }
        result = await client.create_recipe(payload)
        print(f"created recipe id={result.get('id')} name={result.get('name')!r}")

        # --- update recipes 1–4 with steps ---
        for recipe_id, recipe_data in RECIPE_STEPS.items():
            description = _steps_to_description(recipe_data["steps"])
            try:
                result = await client.update_recipe(
                    recipe_id, {"description": description}
                )
                print(f"updated recipe id={recipe_id} name={result.get('name')!r}")
            except Exception as e:
                print(f"skip update id={recipe_id}: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
