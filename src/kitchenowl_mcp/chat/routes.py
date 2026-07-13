import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)

from ..config import get_settings
from . import agent, auth
from .sessions import get_or_create_session

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "chat"


async def chat_page(request: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def login_page(request: Request, error: str | None = None) -> HTMLResponse:
    settings = get_settings()
    template = (STATIC_DIR / "login.html").read_text()

    error_banner = f'<div class="error-banner">{error}</div>' if error else ""

    password_form = ""
    if settings.chat_shared_password:
        password_form = (
            '<form method="post" action="/chat/login">'
            '<input type="password" name="password" '
            'placeholder="Household password" autofocus>'
            '<button type="submit" class="primary">Sign in</button>'
            "</form>"
        )

    has_authentik = bool(
        settings.authentik_issuer
        and settings.authentik_client_id
        and settings.authentik_client_secret
    )
    oidc_button = (
        (
            '<form method="get" action="/chat/oidc/login">'
            '<button type="submit">Sign in with Authentik</button>'
            "</form>"
        )
        if has_authentik
        else ""
    )

    divider = '<div class="divider">or</div>' if password_form and oidc_button else ""

    html = (
        template.replace("{error_banner}", error_banner)
        .replace("{password_form}", password_form)
        .replace("{divider}", divider)
        .replace("{oidc_button}", oidc_button)
    )
    return HTMLResponse(html)


async def login_submit(request: Request) -> RedirectResponse | HTMLResponse:
    form = await request.form()
    password = form.get("password", "")
    if auth.check_shared_password(str(password)):
        request.session["authenticated"] = True
        request.session["auth_method"] = "password"
        return RedirectResponse("/chat", status_code=303)
    return await login_page(request, error="Incorrect password")


async def oidc_login(request: Request):
    settings = get_settings()
    redirect_uri = f"{settings.chat_public_base_url.rstrip('/')}/chat/oidc/callback"
    return await auth.get_oauth_client().authorize_redirect(request, redirect_uri)


async def oidc_callback(request: Request) -> RedirectResponse:
    client = auth.get_oauth_client()
    token = await client.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    request.session["authenticated"] = True
    request.session["auth_method"] = "oidc"
    request.session["display_name"] = userinfo.get("email") or userinfo.get(
        "preferred_username", ""
    )
    return RedirectResponse("/chat", status_code=303)


async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/chat/login", status_code=303)


async def api_message(request: Request) -> JSONResponse:
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    session = get_or_create_session(request)
    try:
        result = await agent.handle_user_message(session, message)
    except agent.ConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    except Exception:
        logger.exception("chat message handling failed")
        return JSONResponse({"error": "internal error"}, status_code=502)
    return JSONResponse(result)


async def api_confirm(request: Request) -> JSONResponse:
    body = await request.json()
    tool_use_id = body.get("tool_use_id")
    decision = body.get("decision")
    if decision not in ("confirm", "cancel") or not tool_use_id:
        return JSONResponse(
            {"error": "tool_use_id and decision are required"}, status_code=400
        )

    session = get_or_create_session(request)
    try:
        result = await agent.handle_confirmation(session, tool_use_id, decision)
    except agent.UnknownConfirmationError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception:
        logger.exception("chat confirmation handling failed")
        return JSONResponse({"error": "internal error"}, status_code=502)
    return JSONResponse(result)
