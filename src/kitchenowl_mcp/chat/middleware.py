from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

PUBLIC_CHAT_PATHS = {"/chat/login", "/chat/oidc/login", "/chat/oidc/callback"}


class ChatAuthGateMiddleware:
    """Gates only /chat* paths. Everything else (notably /mcp) passes through
    untouched, regardless of chat session state."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/chat"):
            await self.app(scope, receive, send)
            return

        if scope["path"] in PUBLIC_CHAT_PATHS or scope["path"].startswith(
            "/chat/static"
        ):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        if not request.session.get("authenticated"):
            if scope["path"].startswith("/chat/api"):
                response = JSONResponse({"error": "not authenticated"}, status_code=401)
            else:
                response = RedirectResponse("/chat/login")
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
