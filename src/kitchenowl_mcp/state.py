from .client import KitchenOwlClient

_client: KitchenOwlClient | None = None


def get_client() -> KitchenOwlClient:
    if _client is None:
        raise RuntimeError("KitchenOwl client not initialized — server not started")
    return _client
