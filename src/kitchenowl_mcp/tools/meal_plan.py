from .. import state


async def get_meal_plan(start_date: str, end_date: str) -> list[dict]:
    """Get planned meals in a date range.

    Dates must be in YYYY-MM-DD format. Returns all planner entries between
    start_date and end_date inclusive, each with recipe_id, recipe name, and date.
    """
    entries = await state.get_client().get_planner()
    return [
        e for e in entries if start_date <= e.get("day", e.get("date", "")) <= end_date
    ]


async def add_meal_plan_entry(
    recipe_id: int,
    date: str,
    meal_type: str = "dinner",
    servings: int = 4,
) -> dict:
    """Add a recipe to the meal plan on a specific date.

    date must be in YYYY-MM-DD format. meal_type is a label like "breakfast",
    "lunch", or "dinner". servings is the number of people to cook for.
    Returns the created planner entry.
    """
    payload = {
        "recipe_id": recipe_id,
        "day": date,
        "yields": servings,
        "type": meal_type,
    }
    return await state.get_client().add_planner_entry(payload)
