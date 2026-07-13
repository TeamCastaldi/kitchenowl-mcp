import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from . import state
from .auth import get_token
from .client import KitchenOwlClient
from .config import get_settings, validate_chat_settings
from .tools import registry

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

    if settings.enable_chat_ui:
        from .chat.tool_schemas import prime_tool_schema_cache

        await prime_tool_schema_cache(server)
        logger.info("Chat UI tool schema cache primed")

    try:
        yield
    finally:
        await client.close()
        state._client = None


def _build_server() -> FastMCP:
    server = FastMCP("KitchenOwl", lifespan=lifespan)
    for fn in registry.ALL_TOOLS:
        server.add_tool(fn)
    return server


def _build_asgi_app(server: FastMCP):
    from pathlib import Path

    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles

    from .chat import routes as chat_routes
    from .chat.middleware import ChatAuthGateMiddleware

    settings = get_settings()
    validate_chat_settings(settings)

    static_dir = Path(__file__).resolve().parent / "static" / "chat"
    mcp_app = server.http_app()

    routes = [
        Route("/chat", chat_routes.chat_page, methods=["GET"]),
        Route("/chat/login", chat_routes.login_page, methods=["GET"]),
        Route("/chat/login", chat_routes.login_submit, methods=["POST"]),
        Route("/chat/oidc/login", chat_routes.oidc_login, methods=["GET"]),
        Route("/chat/oidc/callback", chat_routes.oidc_callback, methods=["GET"]),
        Route("/chat/logout", chat_routes.logout, methods=["POST"]),
        Route("/chat/api/message", chat_routes.api_message, methods=["POST"]),
        Route("/chat/api/confirm", chat_routes.api_confirm, methods=["POST"]),
        Mount("/chat/static", app=StaticFiles(directory=str(static_dir))),
        Mount("/", app=mcp_app),  # catch-all — must stay last
    ]
    middleware = [
        Middleware(
            SessionMiddleware,
            secret_key=settings.chat_session_secret,
            session_cookie="kowl_chat_session",
            https_only=settings.chat_session_cookie_secure,
            same_site="lax",
        ),
        Middleware(ChatAuthGateMiddleware),
    ]
    return Starlette(routes=routes, middleware=middleware, lifespan=mcp_app.lifespan)


def main() -> None:
    settings = get_settings()
    server = _build_server()
    if not settings.enable_chat_ui:
        server.run(transport="streamable-http", host="0.0.0.0", port=settings.mcp_port)
        return

    import uvicorn

    uvicorn.run(_build_asgi_app(server), host="0.0.0.0", port=settings.mcp_port)
