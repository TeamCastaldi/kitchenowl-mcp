import secrets
import time
from dataclasses import dataclass, field

from starlette.requests import Request


@dataclass
class PendingConfirmation:
    tool_use_id: str
    tool_name: str
    tool_input: dict


@dataclass
class ChatSession:
    id: str
    authenticated: bool = False
    auth_method: str | None = None  # "password" | "oidc"
    display_name: str = ""
    messages: list[dict] = field(default_factory=list)
    pending_tool_uses: list[PendingConfirmation] = field(default_factory=list)
    pending_ready_results: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


# In-memory, ephemeral by design (v1) — lost on restart/redeploy.
SESSIONS: dict[str, ChatSession] = {}


def get_or_create_session(request: Request) -> ChatSession:
    sid = request.session.get("chat_session_id")
    if sid is None or sid not in SESSIONS:
        sid = secrets.token_urlsafe(24)
        SESSIONS[sid] = ChatSession(id=sid)
        request.session["chat_session_id"] = sid
    return SESSIONS[sid]
