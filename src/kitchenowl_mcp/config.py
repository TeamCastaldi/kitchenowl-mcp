from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    kitchenowl_api_url: str
    kitchenowl_api_token: str
    kitchenowl_household_id: int = 1
    kitchenowl_default_list_id: int = 1
    mcp_port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
