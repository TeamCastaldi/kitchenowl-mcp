import logging

import httpx

logger = logging.getLogger(__name__)


class KitchenOwlClient:
    def __init__(self, base_url: str, token: str, household_id: int = 1) -> None:
        self._base = base_url.rstrip("/")
        self._household = household_id
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def health_check(self) -> None:
        """Verify KitchenOwl is reachable. Raises on failure."""
        url = f"{self._base}/api/household/{self._household}/recipe"
        r = await self._http.get(url, params={"limit": 1})
        r.raise_for_status()
        logger.info("KitchenOwl connection verified at %s", self._base)

    async def list_recipes(self, search: str = "", limit: int = 50) -> list[dict]:
        url = f"{self._base}/api/household/{self._household}/recipe"
        r = await self._http.get(url)
        r.raise_for_status()
        data = r.json()
        recipes: list[dict] = (
            data.get("recipes", data) if isinstance(data, dict) else data
        )
        if search:
            q = search.lower()
            recipes = [
                rec
                for rec in recipes
                if q in (rec.get("name") or "").lower()
                or q in (rec.get("description") or "").lower()
            ]
        return recipes[:limit]

    async def get_recipe(self, recipe_id: int) -> dict:
        r = await self._http.get(f"{self._base}/api/recipe/{recipe_id}")
        r.raise_for_status()
        return r.json()

    async def create_recipe(self, payload: dict) -> dict:
        url = f"{self._base}/api/household/{self._household}/recipe"
        r = await self._http.post(url, json=payload)
        r.raise_for_status()
        return r.json()

    async def get_shopping_list_items(self, list_id: int) -> list[dict]:
        url = f"{self._base}/api/household/{self._household}/shoppinglist"
        r = await self._http.get(url)
        r.raise_for_status()
        lists = r.json()
        for shopping_list in lists:
            if shopping_list.get("id") == list_id:
                return shopping_list.get("items", [])
        return []

    async def add_shopping_item(self, list_id: int, item: dict) -> dict:
        url = f"{self._base}/api/household/{self._household}/item"
        payload = {**item, "shoppinglist": list_id}
        r = await self._http.post(url, json=payload)
        r.raise_for_status()
        return r.json()

    async def remove_shopping_item(self, list_id: int, item_id: int) -> None:
        url = f"{self._base}/api/household/{self._household}/item/{item_id}"
        r = await self._http.delete(url)
        r.raise_for_status()

    async def get_planner(self) -> list[dict]:
        url = f"{self._base}/api/household/{self._household}/planner"
        r = await self._http.get(url)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data.get("plan", data.get("planner", list(data.values())))
        return data

    async def add_planner_entry(self, payload: dict) -> dict:
        url = f"{self._base}/api/household/{self._household}/planner"
        r = await self._http.post(url, json=payload)
        r.raise_for_status()
        return r.json()

    async def list_items(self) -> list[dict]:
        url = f"{self._base}/api/household/{self._household}/item"
        r = await self._http.get(url)
        r.raise_for_status()
        data = r.json()
        return data.get("items", data) if isinstance(data, dict) else data

    async def create_item(self, payload: dict) -> dict:
        url = f"{self._base}/api/household/{self._household}/item"
        r = await self._http.post(url, json=payload)
        r.raise_for_status()
        return r.json()

    async def update_recipe(self, recipe_id: int, payload: dict) -> dict:
        r = await self._http.post(f"{self._base}/api/recipe/{recipe_id}", json=payload)
        r.raise_for_status()
        return r.json()

    async def delete_recipe(self, recipe_id: int) -> None:
        r = await self._http.delete(f"{self._base}/api/recipe/{recipe_id}")
        r.raise_for_status()

    async def list_tags(self) -> list[dict]:
        url = f"{self._base}/api/household/{self._household}/tag"
        r = await self._http.get(url)
        r.raise_for_status()
        data = r.json()
        return data.get("tags", data) if isinstance(data, dict) else data

    async def cook_recipe(self, recipe_id: int) -> dict:
        r = await self._http.post(f"{self._base}/api/recipe/{recipe_id}/cook")
        r.raise_for_status()
        return r.json()
