import anthropic
import httpx
import pytest
from starlette.testclient import TestClient

from kitchenowl_mcp import client as client_module
from kitchenowl_mcp.chat import agent, dispatch, tool_schemas
from kitchenowl_mcp.config import get_settings
from kitchenowl_mcp.server import _build_asgi_app, _build_server


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, id: str, name: str, input: dict) -> None:
        self.id = id
        self.name = name
        self.input = input

    def model_dump(self) -> dict:
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


class FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text

    def model_dump(self) -> dict:
        return {"type": "text", "text": self.text}


class FakeMessage:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


class FakeMessagesResource:
    def __init__(self, responses: list[FakeMessage]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs) -> FakeMessage:
        # snapshot messages — the caller mutates the same list object after
        # this returns (appending the assistant reply), so store a copy.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)


class FakeAnthropicClient:
    def __init__(self, responses: list[FakeMessage]) -> None:
        self.messages = FakeMessagesResource(responses)


@pytest.fixture
def chat_app(monkeypatch):
    monkeypatch.setenv("KITCHENOWL_API_URL", "http://localhost")
    monkeypatch.setenv("KITCHENOWL_API_TOKEN", "test-token")
    monkeypatch.setenv("ENABLE_CHAT_UI", "true")
    monkeypatch.setenv("CHAT_SESSION_SECRET", "test-secret-key-for-sessions")
    monkeypatch.setenv("CHAT_SHARED_PASSWORD", "correct-horse")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()

    async def fake_health_check(self) -> None:
        return None

    monkeypatch.setattr(
        client_module.KitchenOwlClient, "health_check", fake_health_check
    )

    server = _build_server()
    app = _build_asgi_app(server)
    yield app
    get_settings.cache_clear()


def _client(chat_app) -> TestClient:
    return TestClient(chat_app, base_url="https://testserver")


def test_mcp_endpoint_is_never_gated_by_chat_auth(chat_app):
    with _client(chat_app) as client:
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
            headers={"Accept": "application/json, text/event-stream"},
        )
        # Whatever the MCP protocol response is, it must never be intercepted
        # by the chat auth gate (401 / redirect to /chat/login).
        assert resp.status_code != 401
        assert "/chat/login" not in str(resp.history) + resp.headers.get("location", "")


def test_unauthenticated_api_message_returns_401(chat_app):
    with _client(chat_app) as client:
        resp = client.post(
            "/chat/api/message", json={"message": "hi"}, follow_redirects=False
        )
        assert resp.status_code == 401


def test_unauthenticated_api_clear_returns_401(chat_app):
    with _client(chat_app) as client:
        resp = client.post("/chat/api/clear", follow_redirects=False)
        assert resp.status_code == 401


def test_unauthenticated_chat_page_redirects_to_login(chat_app):
    with _client(chat_app) as client:
        resp = client.get("/chat", follow_redirects=False)
        assert resp.status_code in (302, 303, 307)
        assert resp.headers["location"] == "/chat/login"


def test_login_page_is_public(chat_app):
    with _client(chat_app) as client:
        resp = client.get("/chat/login", follow_redirects=False)
        assert resp.status_code == 200


def test_correct_password_authenticates(chat_app):
    with _client(chat_app) as client:
        resp = client.post(
            "/chat/login", data={"password": "correct-horse"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/chat"

        # session cookie now grants access to the chat api
        resp2 = client.get("/chat", follow_redirects=False)
        assert resp2.status_code == 200


def test_wrong_password_does_not_authenticate(chat_app):
    with _client(chat_app) as client:
        resp = client.post(
            "/chat/login", data={"password": "nope"}, follow_redirects=False
        )
        assert resp.status_code == 200  # redisplays login with error
        assert "Incorrect password" in resp.text

        resp2 = client.get("/chat", follow_redirects=False)
        assert resp2.status_code in (302, 303, 307)


def test_oidc_login_404s_when_authentik_not_configured(chat_app):
    with _client(chat_app) as client:
        resp = client.get("/chat/oidc/login", follow_redirects=False)
        assert resp.status_code == 404


def test_oidc_callback_404s_when_authentik_not_configured(chat_app):
    with _client(chat_app) as client:
        resp = client.get("/chat/oidc/callback", follow_redirects=False)
        assert resp.status_code == 404


def test_static_assets_serve_without_auth(chat_app):
    with _client(chat_app) as client:
        for path in ("/chat/static/app.js", "/chat/static/style.css"):
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code == 200


def test_full_conversation_with_destructive_confirmation(chat_app, monkeypatch):
    """End-to-end HTTP round trip: login -> message -> confirmation -> confirm."""
    delete_calls = []

    async def fake_delete_recipe(recipe_id):
        delete_calls.append(recipe_id)
        return {"deleted_recipe_id": recipe_id}

    monkeypatch.setattr(
        dispatch, "TOOL_FUNCTIONS", {"delete_recipe": fake_delete_recipe}
    )
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset({"delete_recipe"}))
    tool_schemas._CACHED_TOOLS = []

    fake = FakeAnthropicClient(
        [
            FakeMessage(
                [FakeToolUseBlock("tu1", "delete_recipe", {"recipe_id": 7})],
                "tool_use",
            ),
            FakeMessage([FakeTextBlock("Deleted the chili recipe.")], "end_turn"),
        ]
    )
    monkeypatch.setattr(agent, "_get_anthropic_client", lambda: fake)

    with _client(chat_app) as client:
        login = client.post(
            "/chat/login", data={"password": "correct-horse"}, follow_redirects=False
        )
        assert login.status_code == 303

        msg_resp = client.post(
            "/chat/api/message", json={"message": "delete the chili recipe"}
        )
        assert msg_resp.status_code == 200
        body = msg_resp.json()
        assert body["type"] == "confirmation_required"
        tool_use_id = body["pending"][0]["tool_use_id"]
        assert delete_calls == []  # not executed until confirmed

        confirm_resp = client.post(
            "/chat/api/confirm",
            json={"tool_use_id": tool_use_id, "decision": "confirm"},
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json() == {
            "type": "message",
            "text": "Deleted the chili recipe.",
        }
        assert delete_calls == [7]


def test_overloaded_anthropic_error_returns_friendly_503(chat_app, monkeypatch):
    class OverloadedMessagesResource:
        async def create(self, **kwargs):
            response = httpx.Response(529, request=httpx.Request("POST", "http://x"))
            raise anthropic.OverloadedError("overloaded", response=response, body=None)

    class OverloadedClient:
        messages = OverloadedMessagesResource()

    monkeypatch.setattr(agent, "_get_anthropic_client", lambda: OverloadedClient())

    with _client(chat_app) as client:
        client.post("/chat/login", data={"password": "correct-horse"})
        resp = client.post("/chat/api/message", json={"message": "hello"})
        assert resp.status_code == 503
        assert "overloaded" in resp.json()["error"].lower()


def test_api_clear_resets_conversation_history(chat_app, monkeypatch):
    tool_schemas._CACHED_TOOLS = []
    fake = FakeAnthropicClient(
        [
            FakeMessage([FakeTextBlock("Hi there!")], "end_turn"),
            FakeMessage([FakeTextBlock("Hi again!")], "end_turn"),
        ]
    )
    monkeypatch.setattr(agent, "_get_anthropic_client", lambda: fake)

    with _client(chat_app) as client:
        client.post("/chat/login", data={"password": "correct-horse"})

        first = client.post("/chat/api/message", json={"message": "hello"})
        assert first.status_code == 200

        clear_resp = client.post("/chat/api/clear")
        assert clear_resp.status_code == 200
        assert clear_resp.json() == {"status": "cleared"}

        second = client.post("/chat/api/message", json={"message": "hello again"})
        assert second.status_code == 200

    # the second call's message history should only contain the new user
    # message and the assistant's reply to it — not the pre-clear turn
    second_call_messages = fake.messages.calls[-1]["messages"]
    assert len(second_call_messages) == 1
    assert second_call_messages[0] == {"role": "user", "content": "hello again"}
