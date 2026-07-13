import pytest

from kitchenowl_mcp.config import (
    Settings,
    is_authentik_configured,
    validate_chat_settings,
)


def _settings(**overrides) -> Settings:
    base = {
        "kitchenowl_api_url": "http://localhost",
        "kitchenowl_api_token": "test-token",
        "enable_chat_ui": True,
        "chat_session_secret": "secret",
        "anthropic_api_key": "sk-ant-test",
    }
    base.update(overrides)
    return Settings(**base)


def test_disabled_chat_ui_skips_validation() -> None:
    validate_chat_settings(Settings(kitchenowl_api_url="x", kitchenowl_api_token="y"))


def test_requires_session_secret() -> None:
    with pytest.raises(ValueError, match="CHAT_SESSION_SECRET"):
        validate_chat_settings(_settings(chat_session_secret=""))


def test_requires_anthropic_api_key() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        validate_chat_settings(_settings(anthropic_api_key=""))


def test_requires_at_least_one_login_method() -> None:
    with pytest.raises(ValueError, match="login method"):
        validate_chat_settings(_settings())


def test_password_only_is_valid() -> None:
    validate_chat_settings(_settings(chat_shared_password="hunter2"))


def test_authentik_without_public_base_url_raises() -> None:
    with pytest.raises(ValueError, match="CHAT_PUBLIC_BASE_URL"):
        validate_chat_settings(
            _settings(
                authentik_issuer="https://auth.example.com/application/o/kowl/",
                authentik_client_id="id",
                authentik_client_secret="secret",
            )
        )


def test_authentik_with_public_base_url_is_valid() -> None:
    validate_chat_settings(
        _settings(
            authentik_issuer="https://auth.example.com/application/o/kowl/",
            authentik_client_id="id",
            authentik_client_secret="secret",
            chat_public_base_url="https://kitchenowl-mcp.example.com",
        )
    )


def test_is_authentik_configured_requires_all_three_fields() -> None:
    assert not is_authentik_configured(_settings())
    assert not is_authentik_configured(
        _settings(authentik_issuer="https://auth.example.com/")
    )
    assert is_authentik_configured(
        _settings(
            authentik_issuer="https://auth.example.com/",
            authentik_client_id="id",
            authentik_client_secret="secret",
        )
    )
