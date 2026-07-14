import time

from kitchenowl_mcp.chat import sessions


class FakeSessionRequest:
    def __init__(self, session: dict) -> None:
        self.session = session


def _reset_sessions() -> None:
    sessions.SESSIONS.clear()


def test_get_or_create_session_reuses_existing_session() -> None:
    _reset_sessions()
    request = FakeSessionRequest({})
    first = sessions.get_or_create_session(request)
    second = sessions.get_or_create_session(request)
    assert first is second
    assert len(sessions.SESSIONS) == 1


def test_prune_sessions_evicts_expired_entries() -> None:
    _reset_sessions()
    sessions.SESSIONS["old"] = sessions.ChatSession(
        id="old",
        last_active=0.0,  # far in the past -> expired
    )
    sessions.SESSIONS["fresh"] = sessions.ChatSession(id="fresh")

    sessions._prune_sessions()

    assert "old" not in sessions.SESSIONS
    assert "fresh" in sessions.SESSIONS


def test_prune_sessions_enforces_max_size() -> None:
    _reset_sessions()
    now = time.time()
    total = sessions.MAX_SESSIONS + 5
    for i in range(total):
        sid = f"s{i}"
        # Recent enough to survive TTL pruning; ordered so s0 is oldest.
        sessions.SESSIONS[sid] = sessions.ChatSession(
            id=sid, last_active=now - (total - i)
        )

    sessions._prune_sessions()

    assert len(sessions.SESSIONS) == sessions.MAX_SESSIONS
    # the oldest (lowest last_active) entries were the ones evicted
    assert "s0" not in sessions.SESSIONS
    assert f"s{total - 1}" in sessions.SESSIONS


def test_reset_session_clears_messages_and_pending_state() -> None:
    session = sessions.ChatSession(
        id="s1",
        messages=[{"role": "user", "content": "hi"}],
        pending_tool_uses=[sessions.PendingConfirmation("tu1", "delete_recipe", {})],
        pending_ready_results=[{"type": "tool_result"}],
    )

    sessions.reset_session(session)

    assert session.messages == []
    assert session.pending_tool_uses == []
    assert session.pending_ready_results == []
