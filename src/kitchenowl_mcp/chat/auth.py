import secrets

from authlib.integrations.starlette_client import OAuth

from ..config import get_settings

_oauth: OAuth | None = None


def check_shared_password(password: str) -> bool:
    expected = get_settings().chat_shared_password
    if not expected:
        return False
    return secrets.compare_digest(password, expected)


def get_oauth_client():
    """Lazily register and return the Authentik OIDC client (Authlib)."""
    global _oauth
    if _oauth is None:
        settings = get_settings()
        _oauth = OAuth()
        _oauth.register(
            name="authentik",
            server_metadata_url=(
                f"{settings.authentik_issuer.rstrip('/')}"
                "/.well-known/openid-configuration"
            ),
            client_id=settings.authentik_client_id,
            client_secret=settings.authentik_client_secret,
            client_kwargs={"scope": "openid profile email"},
        )
    return _oauth.authentik
