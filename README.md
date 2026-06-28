# kitchenowl-mcp

An MCP (Model Context Protocol) server that connects Claude to a household [KitchenOwl](https://kitchenowl.org) instance. Enables read/write access to recipes, shopping lists, and meal plans from within a Claude conversation.

Deployed alongside KitchenOwl in a home Docker Compose stack, exposed to claude.ai via Traefik.

---

## Tools

| Tool | Description |
|------|-------------|
| `search_recipes` | List all recipes or filter by keyword / tag |
| `get_recipe` | Fetch a recipe by ID (includes ingredients and steps) |
| `create_recipe` | Create a new recipe with ingredients, steps, and tags |
| `update_recipe` | Update a recipe's description, steps, or other fields |
| `list_tags` | List all household recipe tags |
| `mark_recipe_made` | Log a cook event (sets `planned=true` on the recipe) |
| `delete_recipe` | Delete a recipe by ID |
| `get_shopping_list` | Read the current shopping list |
| `add_shopping_list_items` | Add items with optional amounts and units |
| `clear_checked_items` | Remove checked items from the shopping list |
| `get_meal_plan` | Fetch planned meals for a date range |
| `add_meal_plan_entry` | Add a recipe to the meal plan for a specific day |

## Stack

- **Runtime:** Python 3.11+
- **MCP framework:** FastMCP 2.x (streamable-http transport)
- **HTTP client:** httpx (async)
- **Config:** pydantic-settings (`KITCHENOWL_*` env vars)
- **Linter/formatter:** ruff
- **Tests:** pytest

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/ncastaldi/kitchenowl-mcp
cd kitchenowl-mcp

# 2. Copy environment template and fill in values
cp .env.example .env

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Run the server
kitchenowl-mcp
```

The server listens on port 8000 (streamable-http transport).

## Docker Compose deployment

```yaml
services:
  kitchenowl-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      KITCHENOWL_API_URL: http://kitchenowl-back:5000
      KITCHENOWL_API_TOKEN: your_token_here
      KITCHENOWL_HOUSEHOLD_ID: 1
      KITCHENOWL_DEFAULT_LIST_ID: 1
    depends_on:
      - kitchenowl-back
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KITCHENOWL_API_URL` | Yes | Base URL of the KitchenOwl backend |
| `KITCHENOWL_API_TOKEN` | Yes | Bearer token for KitchenOwl API auth |
| `KITCHENOWL_HOUSEHOLD_ID` | No | Household ID (default: `1`) |
| `KITCHENOWL_DEFAULT_LIST_ID` | No | ID of the shopping list to use (default: `1`) |

## Architecture

```
claude.ai
    │  HTTP/SSE (remote MCP, streamable-http)
    ▼
kitchenowl-mcp  (container, port 8000)
    │  HTTP REST + Bearer token
    │  internal Docker network only
    ▼
kitchenowl-back  (KitchenOwl container)
```

## Project structure

```
src/kitchenowl_mcp/
  config.py      pydantic-settings config
  auth.py        token seam (v2: per-user lookup)
  client.py      all KitchenOwl HTTP calls
  state.py       shared client singleton
  server.py      FastMCP app, lifespan, tool registration
  tools/
    recipes.py   search, get, create, update, list_tags, mark_made, delete
    shopping.py  get_list, add_items, clear_checked
    meal_plan.py get_plan, add_entry
```

## Development

```bash
# Lint
ruff check .
ruff format .

# Tests
pytest
```

## Known gaps

- `clear_checked_items` cannot be fully stress-tested end-to-end — there is no MCP tool to mark a shopping list item as checked. Add `check_shopping_item` to close the loop.
- `mark_recipe_made` sets `planned=true` and appends to `planned_cooking_dates` rather than writing to a discrete cook-history log. This matches observed KitchenOwl API behavior.
