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
    messages: list[dict] = field(default_factory=list)
    pending_tool_uses: list[PendingConfirmation] = field(default_factory=list)
    pending_ready_results: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


# In-memory, ephemeral by design (v1) — lost on restart/redeploy. Bounded by
# TTL + max-size pruning below so a long-running deployment can't grow
# unboundedly from repeat visits or bots hitting the login/chat endpoints.
SESSIONS: dict[str, ChatSession] = {}

SESSION_TTL_SECONDS = 24 * 60 * 60
MAX_SESSIONS = 500


def _prune_sessions() -> None:
    now = time.time()
    expired = [
        sid for sid, s in SESSIONS.items() if now - s.last_active > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del SESSIONS[sid]

    overflow = len(SESSIONS) - MAX_SESSIONS
    if overflow > 0:
        oldest = sorted(SESSIONS.values(), key=lambda s: s.last_active)[:overflow]
        for s in oldest:
            del SESSIONS[s.id]


def reset_session(session: ChatSession) -> None:
    session.messages = []
    session.pending_tool_uses = []
    session.pending_ready_results = []


def get_or_create_session(request: Request) -> ChatSession:
    sid = request.session.get("chat_session_id")
    if sid is None or sid not in SESSIONS:
        _prune_sessions()
        sid = secrets.token_urlsafe(24)
        SESSIONS[sid] = ChatSession(id=sid)
        request.session["chat_session_id"] = sid
    session = SESSIONS[sid]
    session.last_active = time.time()
    return session
