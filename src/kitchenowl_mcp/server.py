import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from . import state
from .auth import get_token
from .client import KitchenOwlClient
from .config import get_settings
from .tools import meal_plan, recipes, shopping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
    settings = get_settings()
    client = KitchenOwlClient(
        base_url=settings.kitchenowl_api_url,
        token=get_token(),
        household_id=settings.kitchenowl_household_id,
    )
    logger.info("Connecting to KitchenOwl at %s ...", settings.kitchenowl_api_url)
    await client.health_check()
    state._client = client
    try:
        yield
    finally:
        await client.close()
        state._client = None


def _build_server() -> FastMCP:
    server = FastMCP("KitchenOwl", lifespan=lifespan)

    # Recipes
    server.add_tool(recipes.search_recipes)
    server.add_tool(recipes.get_recipe)
    server.add_tool(recipes.create_recipe)
    server.add_tool(recipes.update_recipe)
    server.add_tool(recipes.delete_recipe)
    server.add_tool(recipes.list_tags)
    server.add_tool(recipes.mark_recipe_made)

    # Shopping list
    server.add_tool(shopping.get_shopping_list)
    server.add_tool(shopping.add_shopping_list_items)
    server.add_tool(shopping.clear_checked_items)

    # Meal plan
    server.add_tool(meal_plan.get_meal_plan)
    server.add_tool(meal_plan.add_meal_plan_entry)

    return server


def main() -> None:
    settings = get_settings()
    server = _build_server()
    server.run(transport="streamable-http", host="0.0.0.0", port=settings.mcp_port)
