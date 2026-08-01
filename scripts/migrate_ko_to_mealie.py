#!/usr/bin/env python3
"""One-off migration: KitchenOwl recipe dump -> Mealie.

Usage:
    export MEALIE_BASE_URL=https://mealie.castaldifamily.com
    export MEALIE_API_KEY=...
    python migrate_ko_to_mealie.py --limit 3          # test batch
    python migrate_ko_to_mealie.py                    # full run
    python migrate_ko_to_mealie.py --only 1,6,25       # specific recipe ids

Input data lives in ko_recipes_full.json (list of KO get_recipe() payloads,
each with an extra "id" key), built from kitchenowl-mcp tool output.

Foods/units must be created via their own endpoints before being referenced
by id in a recipe PATCH -- inline {"name": ...} dicts work for tags/categories
but raise a server-side ValueError for foods/units (confirmed against a live
v3.21.0 instance).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx

DATA_FILE = Path(__file__).parent / "ko_recipes_full.json"

# tag name (lowercased) -> canonical Mealie tag name, or None to drop entirely
TAG_MAP = {
    "chicken": "Chicken",
    "grill": "Grill",
    "seafood": "Seafood",
    "summer": "Summer",
    "quick": "Quick",
    "high-protein": "High-Protein",
    "higher protein": "High-Protein",
    "mcp-test": None,
    "temporary": None,
    "breakfast": None,  # promoted to category instead, see CATEGORY_TAGS
    "technique": None,  # promoted to category instead, see CATEGORY_TAGS
    # cast iron/grill/skillet/wok are intercepted by TOOL_TAGS before this
    # map is consulted -- not listed here since that branch never falls
    # through to TAG_MAP for those keys.
}
CATEGORY_TAGS = {"breakfast": "Breakfast", "technique": "Technique"}

# equipment tags -> Mealie tools (kitchen.org/api/organizers/tools), a
# separate facet from tags/categories -- these are physical equipment, not
# descriptive/dietary/cuisine tags.
TOOL_TAGS = {
    "cast iron": "Cast Iron",
    "grill": "Grill",
    "skillet": "Skillet",
    "wok": "Wok",
}

# meal-type/course category, applied unconditionally per KO recipe id -- not
# derivable from tags since KO has no "dinner"/"side"/"sauce" tag convention.
# Recipes that get Breakfast via CATEGORY_TAGS (the "breakfast" KO tag) are
# omitted here rather than duplicated.
RECIPE_BASE_CATEGORY: dict[int, str] = {
    6: "Dinner",
    7: "Dinner",
    8: "Dinner",
    9: "Dinner",
    10: "Dinner",
    11: "Dinner",
    12: "Sauce",
    13: "Dinner",
    14: "Dinner",
    15: "Dinner",
    16: "Dinner",
    17: "Side",
    18: "Dinner",
    20: "Dinner",
    21: "Dinner",
    22: "Dinner",
    23: "Dinner",
    24: "Dinner",
    25: "Dinner",
}

# recipeServings per KO id -- explicit count stated by the recipe, or a
# discrete/packaged-goods count we can trust (fillets, breasts, tostadas,
# patties, meatballs-per-serving, a standard 12oz pasta/noodle box).
# Anything absent here falls back to BREAKFAST_DEFAULT_SERVINGS (Breakfast
# category recipes -- personal, cook-for-yourself technique lessons) or
# HOUSEHOLD_DEFAULT_SERVINGS (everything else -- family dinner recipes).
# Weight-only amounts (lb of ground beef/thighs) aren't a reliable enough
# signal to guess a serving count from -- appetite varies too much to trust
# that conversion.
BREAKFAST_DEFAULT_SERVINGS = 1
HOUSEHOLD_DEFAULT_SERVINGS = 4
RECIPE_SERVINGS: dict[int, int] = {
    6: 3,  # Pan Sauce Lesson -- description states "Serves 3"
    11: 4,  # Grilled Salmon with Dill Chimichurri -- 4 fillets
    12: 4,  # Chimichurri -- description states "4 servings"
    13: 4,  # Canned Tuna Tostadas -- 4 tostadas
    14: 4,  # Orecchiette w/ Fresh Corn Alfredo -- 12oz pasta box convention
    16: 4,  # Cold Sesame Rice Noodles -- 12oz noodles, same convention
    18: 4,  # Italian-American Meatballs -- ~16-18 meatballs, ~4/serving
    19: 1,  # Overnight Oats -- single-jar prep
    20: 3,  # Spice-Rubbed Chicken Thighs -- description states "dinner for 3"
    23: 4,  # Katsu Chicken Curry -- 4 chicken breasts
    24: 4,  # Grilled Beef & Chicken Burgers -- description states "~4-5"; 4-5 patties
}

UNIT_ALIASES = {
    "tbsp": "tablespoon",
    "tablespoons": "tablespoon",
    "tablespoon": "tablespoon",
    "tsp": "teaspoon",
    "teaspoons": "teaspoon",
    "teaspoon": "teaspoon",
    "cup": "cup",
    "cups": "cup",
    "lb": "pound",
    "lbs": "pound",
    "pound": "pound",
    "pounds": "pound",
    "oz": "ounce",
    "ounces": "ounce",
    "ounce": "ounce",
    "g": "gram",
    "gram": "gram",
    "grams": "gram",
    "ml": "milliliter",
    "clove": "clove",
    "cloves": "clove",
    "sprig": "sprig",
    "sprigs": "sprig",
}

# (name, amount, unit, note) tuples -- hand-parsed from KO free text, keyed by
# KO recipe id + item name. Anything not listed here falls back to a bare
# qty=0/no-unit ingredient with the original KO name preserved as the food name.
INGREDIENT_OVERRIDES: dict[int, dict[str, tuple[float, str | None, str]]] = {
    1: {
        "Eggs": (2, None, "")
    },  # Scrambled Eggs -- KO gave no count; 2 eggs is the standard single serving
    2: {"Eggs": (2, None, "")},  # Fried Eggs -- same
    3: {"Eggs": (2, None, "")},  # Hard Boiled Eggs -- same
    4: {"Eggs": (2, None, "")},  # Classic Omelet -- steps already say "Whisk 2 eggs"
    5: {
        "eggs (2 per person)": (2, None, "2 per person"),
        "bread or toast (optional, for serving)": (0, None, "optional, for serving"),
        "fresh herbs (optional garnish)": (0, None, "optional garnish"),
    },
    6: {
        "Earth Balance or Miyoko's butter (2 tbsp) — dairy-free, works identically to butter here": (
            2,
            "tbsp",
            "Earth Balance or Miyoko's butter — dairy-free, works identically to butter",
        ),
        "boneless skinless chicken thighs (about 1.5 lb)": (
            1.5,
            "lb",
            "boneless skinless chicken thighs",
        ),
        "fresh parsley, chopped (for garnish)": (
            0,
            None,
            "fresh parsley, chopped, for garnish",
        ),
        "fresh thyme (3–4 sprigs, or 1/2 tsp dried)": (
            3,
            "sprig",
            "fresh thyme (3-4 sprigs, or 1/2 tsp dried)",
        ),
        "garlic cloves, minced (3 cloves)": (3, "clove", "garlic, minced"),
        "lemon juice (1 tbsp, about half a lemon)": (
            1,
            "tbsp",
            "lemon juice (about half a lemon)",
        ),
        "low-sodium chicken broth (3/4 cup)": (0.75, "cup", "low-sodium chicken broth"),
        "olive oil (1 tbsp)": (1, "tbsp", "olive oil"),
    },
    25: {
        "fresh ginger, grated": (1, "tbsp", "fresh ginger, grated"),
        "garlic, minced": (3, "clove", "garlic, minced"),
        "large shrimp, peeled and deveined (or boneless skinless chicken thighs)": (
            1,
            "lb",
            "1-1.5 lb, peeled and deveined (or boneless skinless chicken thighs)",
        ),
        "neutral oil, for grilling": (0, None, "neutral oil, for grilling, to taste"),
        "scallions, sliced (for garnish)": (2, None, "scallions, sliced, for garnish"),
        "toasted sesame seeds (for garnish)": (
            1,
            "tbsp",
            "toasted sesame seeds, for garnish",
        ),
    },
    9: {
        "egg (for egg wash, optional)": (0, None, "for egg wash, optional"),
        "flour (2 tbsp for thickening)": (2, "tbsp", "for thickening"),
        "frozen puff pastry (1 sheet)": (1, None, "1 sheet"),
        "oat milk or coconut cream (dairy-free swap for heavy cream)": (
            0,
            None,
            "dairy-free swap for heavy cream",
        ),
    },
    11: {
        "vegetable oil (for grill)": (0, None, "for grill"),
        "skin-on salmon fillets": (
            4,
            None,
            "4 skin-on, 6-8 oz fillets, pin bones removed",
        ),
    },
    12: {
        "fresh oregano (optional)": (0, None, "optional"),
        "lemon (optional, for variation)": (0, None, "optional, for variation"),
    },
    16: {
        "rice noodles (12 oz)": (12, "oz", ""),
    },
    18: {
        "Italian seasoning": (1.5, "tbsp", "1.5 to 2 tbsp"),
        "ground chuck (80/20)": (1, "lb", "80/20"),
        "milk or broth, for panade": (0.25, "cup", "for panade"),
        "minced garlic": (1, "tsp", "1 to 1.5 tsp"),
        "panko breadcrumbs": (0.75, "cup", "3/4 to 1 cup"),
    },
    19: {
        "milk (or plant milk)": (0, None, "or plant milk"),
        "mix-ins of choice (fruit, nut butter, spices, nuts)": (
            0,
            None,
            "fruit, nut butter, spices, nuts",
        ),
    },
    20: {
        "Chicken thighs": (9, None, "8-10 chicken thighs"),
    },
}

# Chinese Mince and its skillet variant share the exact same ingredient list.
_CHINESE_MINCE_OVERRIDES = {
    "Shaoxing wine or dry sherry (optional), 1 tbsp": (1, "tbsp", "optional"),
    "bamboo shoots (optional)": (0, None, "optional"),
    "bean sprouts (optional)": (0, None, "optional"),
    "bell pepper, diced (optional)": (0, None, "diced, optional"),
    "carrots, diced or julienned (optional)": (0, None, "diced or julienned, optional"),
    "celery, diced (optional)": (0, None, "diced, optional"),
    "cooked lo mein or thin egg noodles, 8 oz (optional, for noodle variation)": (
        8,
        "oz",
        "optional, for noodle variation",
    ),
    "cornstarch, 1 tsp, mixed with 2 tbsp water": (1, "tsp", "mixed with 2 tbsp water"),
    "dark soy sauce or hoisin sauce (optional, for extra savory depth), 1 tsp": (
        1,
        "tsp",
        "optional, for extra savory depth",
    ),
    "fresh ginger, 1 tbsp, minced": (1, "tbsp", "minced"),
    "frozen peas (optional), 1/2 cup": (0.5, "cup", "optional"),
    "garlic, 2 to 3 cloves, minced": (2, "clove", "2 to 3 cloves, minced"),
    "green onions (scallions), 4 to 6, sliced, white and green parts separated": (
        4,
        None,
        "4 to 6, sliced, white and green parts separated",
    ),
    "ground beef, 1 lb": (1, "lb", ""),
    "mushrooms, sliced (optional)": (0, None, "sliced, optional"),
    "neutral oil (vegetable or peanut), 2 tbsp": (2, "tbsp", "vegetable or peanut"),
    "oyster sauce, 1 to 2 tbsp": (1, "tbsp", "1 to 2 tbsp"),
    "snow peas (optional)": (0, None, "optional"),
    "soy sauce, 3 tbsp": (3, "tbsp", ""),
    "steamed white rice, for serving": (0, None, "for serving"),
    "sugar, 1/2 tsp": (0.5, "tsp", ""),
    "water chestnuts, diced (optional), 1/2 cup": (0.5, "cup", "diced, optional"),
    "white pepper or black pepper, to taste": (0, None, "to taste"),
}
INGREDIENT_OVERRIDES[21] = _CHINESE_MINCE_OVERRIDES
INGREDIENT_OVERRIDES[22] = _CHINESE_MINCE_OVERRIDES

INGREDIENT_OVERRIDES[23] = {
    "bay leaf, 1": (1, None, ""),
    "breadcrumbs, 100 g": (100, "g", ""),
    "carrot, 2, sliced": (2, None, "sliced"),
    "chicken breast, 4, pounded to 1cm thickness": (
        4,
        None,
        "pounded to 1cm thickness",
    ),
    "chicken stock, 600 ml": (600, "ml", ""),
    "curry powder, 4 teaspoons": (4, "tsp", ""),
    "egg, 1, beaten": (1, None, "beaten"),
    "garam masala, 1 teaspoon": (1, "tsp", ""),
    "garlic cloves, 5, chopped": (5, "clove", "chopped"),
    "honey, 2 teaspoons": (2, "tsp", ""),
    "onions, 2, sliced": (2, None, "sliced"),
    "plain flour, 2 tablespoons (for coating chicken)": (
        2,
        "tbsp",
        "for coating chicken",
    ),
    "plain flour, 2 tablespoons (for curry sauce)": (2, "tbsp", "for curry sauce"),
    "salt and pepper, to taste": (0, None, "to taste"),
    "soy sauce, 4 teaspoons": (4, "tsp", ""),
    "sunflower oil, 2 tablespoons": (2, "tbsp", ""),
    "vegetable oil, 230 ml (for frying chicken)": (230, "ml", "for frying chicken"),
    "white rice, for serving": (0, None, "for serving"),
}

INGREDIENT_OVERRIDES[24] = {
    "Montreal steak seasoning": (1.5, "tbsp", "1.5-2 tbsp"),
    "olive oil (for relish)": (1, "tbsp", "for relish, or reserved from cooking"),
}
# quantity comes from KO's own `description` field when present (recipe 25's
# style); those entries above only carry unit/note overrides.


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s


class MealieClient:
    def __init__(self, base_url: str, api_key: str):
        self.http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        self._tag_cache: dict[str, dict] = {}
        self._category_cache: dict[str, dict] = {}
        self._food_cache: dict[str, dict] = {}
        self._unit_cache: dict[str, dict] = {}
        self._tool_cache: dict[str, dict] = {}

    def _get_or_create(
        self,
        cache: dict,
        list_path: str,
        create_path: str,
        name: str,
        extra: dict | None = None,
    ) -> dict:
        key = name.strip().lower()
        if key in cache:
            return cache[key]
        r = self.http.get(list_path, params={"search": name, "perPage": 50})
        r.raise_for_status()
        for item in r.json().get("items", []):
            if item["name"].strip().lower() == key:
                cache[key] = item
                return item
        payload = {"name": name}
        if extra:
            payload.update(extra)
        r = self.http.post(create_path, json=payload)
        r.raise_for_status()
        item = r.json()
        cache[key] = item
        return item

    def get_or_create_tag(self, name: str) -> dict:
        return self._get_or_create(
            self._tag_cache, "/api/organizers/tags", "/api/organizers/tags", name
        )

    def get_or_create_category(self, name: str) -> dict:
        return self._get_or_create(
            self._category_cache,
            "/api/organizers/categories",
            "/api/organizers/categories",
            name,
        )

    def get_or_create_food(self, name: str) -> dict:
        return self._get_or_create(self._food_cache, "/api/foods", "/api/foods", name)

    def get_or_create_unit(self, name: str) -> dict:
        abbrev = "".join(w[0] for w in name.split()) if len(name) > 8 else name
        return self._get_or_create(
            self._unit_cache, "/api/units", "/api/units", name, {"abbreviation": abbrev}
        )

    def get_or_create_tool(self, name: str) -> dict:
        # like foods/units (not tags/categories) -- must be pre-created and
        # referenced by id, an inline {"name": ...} dict is silently dropped.
        return self._get_or_create(
            self._tool_cache, "/api/organizers/tools", "/api/organizers/tools", name
        )

    def create_recipe_stub(self, name: str) -> str:
        r = self.http.post("/api/recipes", json={"name": name})
        r.raise_for_status()
        return r.json().strip('"') if r.text.startswith('"') else r.json()

    def recipe_exists(self, slug: str) -> bool:
        r = self.http.get(f"/api/recipes/{slug}")
        return r.status_code == 200

    def update_recipe(self, slug: str, payload: dict) -> dict:
        r = self.http.patch(f"/api/recipes/{slug}", json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"PATCH {slug} failed: {r.status_code} {r.text}")
        return r.json()


def build_ingredient(client: MealieClient, ko_id: int, item: dict) -> dict:
    name = item["name"]
    override = INGREDIENT_OVERRIDES.get(ko_id, {}).get(name)
    ko_desc = (item.get("description") or "").strip()

    if override:
        qty, unit_name, note = override
        if ko_desc:
            m = re.match(r"^([\d./]+)\s*(\D*)$", ko_desc)
            if m and m.group(1):
                try:
                    qty = (
                        eval(m.group(1), {"__builtins__": {}})
                        if "/" in m.group(1)
                        else float(m.group(1))
                    )
                except Exception:
                    pass
        food_name = re.sub(r"\s*\([^)]*\)", "", name).split(",")[0].strip() or name
    elif ko_desc:
        m = re.match(r"^([\d./]+)\s*([a-zA-Z]*)", ko_desc)
        qty, unit_name = 0.0, None
        if m and m.group(1):
            try:
                qty = (
                    eval(m.group(1), {"__builtins__": {}})
                    if "/" in m.group(1)
                    else float(m.group(1))
                )
            except Exception:
                qty = 0.0
            if m.group(2):
                unit_name = UNIT_ALIASES.get(m.group(2).lower())
        food_name = name
        note = ko_desc if not m or not m.group(1) else ""
    else:
        qty, unit_name, note = 0.0, None, ""
        food_name = name

    food = client.get_or_create_food(food_name)
    ing = {
        "quantity": qty,
        "food": {"id": food["id"], "name": food["name"]},
        "note": note,
        "display": food_name,
    }
    if unit_name:
        canon = UNIT_ALIASES.get(unit_name.lower(), unit_name)
        unit = client.get_or_create_unit(canon)
        ing["unit"] = {"id": unit["id"], "name": unit["name"]}
    return ing


def build_tags_and_categories(
    client: MealieClient, ko_id: int, ko_tags: list[str]
) -> tuple[list[dict], list[dict], list[dict]]:
    tags, categories, tools = [], [], []
    seen_tags, seen_cats, seen_tools = set(), set(), set()

    base_cat_name = RECIPE_BASE_CATEGORY.get(ko_id)
    if base_cat_name:
        cat = client.get_or_create_category(base_cat_name)
        categories.append({"id": cat["id"], "name": cat["name"], "slug": cat["slug"]})
        seen_cats.add(base_cat_name)

    for t in ko_tags:
        key = t.strip().lower()
        if key in CATEGORY_TAGS:
            cat_name = CATEGORY_TAGS[key]
            if cat_name not in seen_cats:
                cat = client.get_or_create_category(cat_name)
                categories.append(
                    {"id": cat["id"], "name": cat["name"], "slug": cat["slug"]}
                )
                seen_cats.add(cat_name)
            continue
        if key in TOOL_TAGS:
            tool_name = TOOL_TAGS[key]
            if tool_name not in seen_tools:
                tool = client.get_or_create_tool(tool_name)
                tools.append(
                    {"id": tool["id"], "name": tool["name"], "slug": tool["slug"]}
                )
                seen_tools.add(tool_name)
            continue
        mapped = TAG_MAP.get(key, t)
        if mapped is None:
            continue
        if mapped not in seen_tags:
            tag = client.get_or_create_tag(mapped)
            tags.append({"id": tag["id"], "name": tag["name"], "slug": tag["slug"]})
            seen_tags.add(mapped)
    return tags, categories, tools


def migrate_recipe(client: MealieClient, ko: dict, dry_run: bool) -> None:
    ko_id = ko["id"]
    name = ko["name"]
    slug = slugify(name)
    print(f"[{ko_id}] {name} -> slug={slug}")

    ingredients = [build_ingredient(client, ko_id, item) for item in ko["items"]]
    tags, categories, tools = build_tags_and_categories(
        client, ko_id, ko.get("tags", [])
    )
    instructions = [{"text": s} for s in ko.get("steps", [])]

    if ko_id in RECIPE_SERVINGS:
        servings = RECIPE_SERVINGS[ko_id]
    elif any(c["name"] == "Breakfast" for c in categories):
        servings = BREAKFAST_DEFAULT_SERVINGS
    else:
        servings = HOUSEHOLD_DEFAULT_SERVINGS
    payload = {
        "name": name,
        "description": ko.get("description") or "",
        "recipeCategory": categories,
        "tags": tags,
        "tools": tools,
        "recipeIngredient": ingredients,
        "recipeInstructions": instructions,
        "recipeServings": servings,
        "recipeYieldQuantity": servings,
        "recipeYield": f"{servings} servings",
    }

    if dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print()
        return

    if not client.recipe_exists(slug):
        client.create_recipe_stub(name)
    client.update_recipe(slug, payload)
    print(
        f"  -> pushed ({len(ingredients)} ingredients, {len(instructions)} steps, "
        f"{len(tags)} tags, {len(categories)} categories, {len(tools)} tools)"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--limit", type=int, default=None, help="only migrate the first N recipes"
    )
    ap.add_argument(
        "--only", type=str, default=None, help="comma-separated KO recipe ids"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print payloads, don't call Mealie"
    )
    args = ap.parse_args()

    base_url = os.environ["MEALIE_BASE_URL"]
    api_key = os.environ["MEALIE_API_KEY"]
    recipes = json.loads(DATA_FILE.read_text())

    if args.only:
        wanted = {int(x) for x in args.only.split(",")}
        recipes = [r for r in recipes if r["id"] in wanted]
    if args.limit:
        recipes = recipes[: args.limit]

    client = MealieClient(base_url, api_key)
    for ko in recipes:
        migrate_recipe(client, ko, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
