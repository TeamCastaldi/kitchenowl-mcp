from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    kitchenowl_api_url: str
    kitchenowl_api_token: str
    kitchenowl_household_id: int = 1
    kitchenowl_default_list_id: int = 1
    mcp_port: int = 8000

    # Chat UI (optional, default disabled)
    enable_chat_ui: bool = False
    chat_shared_password: str = ""
    chat_session_secret: str = ""
    chat_public_base_url: str = ""

    # Authentik OIDC login for the chat UI
    authentik_issuer: str = ""
    authentik_client_id: str = ""
    authentik_client_secret: str = ""

    # Anthropic (chat UI agent loop)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    chat_max_tokens: int = 4096
    chat_max_tool_rounds: int = 8


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def validate_chat_settings(settings: Settings) -> None:
    """Fail loudly at startup if chat UI is enabled but misconfigured."""
    if not settings.enable_chat_ui:
        return
    if not settings.chat_session_secret:
        raise ValueError("CHAT_SESSION_SECRET is required when ENABLE_CHAT_UI=true")
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is required when ENABLE_CHAT_UI=true")

    has_password = bool(settings.chat_shared_password)
    has_authentik = bool(
        settings.authentik_issuer
        and settings.authentik_client_id
        and settings.authentik_client_secret
    )
    if not has_password and not has_authentik:
        raise ValueError(
            "At least one chat login method is required when ENABLE_CHAT_UI=true: "
            "set CHAT_SHARED_PASSWORD, or all of AUTHENTIK_ISSUER/"
            "AUTHENTIK_CLIENT_ID/AUTHENTIK_CLIENT_SECRET"
        )
