import asyncio

import pytest

from kitchenowl_mcp.chat import agent, dispatch, sessions, tool_schemas
from kitchenowl_mcp.config import get_settings


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
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeAnthropicClient:
    def __init__(self, responses: list[FakeMessage]) -> None:
        self.messages = FakeMessagesResource(responses)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    monkeypatch.setenv("KITCHENOWL_API_URL", "http://localhost")
    monkeypatch.setenv("KITCHENOWL_API_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("CHAT_MAX_TOOL_ROUNDS", "3")
    get_settings.cache_clear()
    tool_schemas._CACHED_TOOLS = []
    yield
    get_settings.cache_clear()
    tool_schemas._CACHED_TOOLS = None


def _install_fake_client(
    monkeypatch, responses: list[FakeMessage]
) -> FakeAnthropicClient:
    fake = FakeAnthropicClient(responses)
    monkeypatch.setattr(agent, "_get_anthropic_client", lambda: fake)
    return fake


def _new_session() -> sessions.ChatSession:
    return sessions.ChatSession(id="s1")


def test_non_destructive_tool_executes_and_loop_continues(monkeypatch):
    calls = []

    async def fake_search_recipes(**kwargs):
        calls.append(kwargs)
        return {"recipes": []}

    monkeypatch.setattr(
        dispatch, "TOOL_FUNCTIONS", {"search_recipes": fake_search_recipes}
    )
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset())

    _install_fake_client(
        monkeypatch,
        [
            FakeMessage(
                [FakeToolUseBlock("tu1", "search_recipes", {"query": "chili"})],
                "tool_use",
            ),
            FakeMessage([FakeTextBlock("Found no chili recipes.")], "end_turn"),
        ],
    )

    session = _new_session()
    result = asyncio.run(agent.handle_user_message(session, "find chili recipes"))

    assert result == {"type": "message", "text": "Found no chili recipes."}
    assert calls == [{"query": "chili"}]


def test_destructive_tool_requires_confirmation_without_executing(monkeypatch):
    calls = []

    async def fake_delete_recipe(recipe_id):
        calls.append(recipe_id)
        return {"deleted_recipe_id": recipe_id}

    monkeypatch.setattr(
        dispatch, "TOOL_FUNCTIONS", {"delete_recipe": fake_delete_recipe}
    )
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset({"delete_recipe"}))

    _install_fake_client(
        monkeypatch,
        [
            FakeMessage(
                [FakeToolUseBlock("tu1", "delete_recipe", {"recipe_id": 5})], "tool_use"
            )
        ],
    )

    session = _new_session()
    result = asyncio.run(agent.handle_user_message(session, "delete recipe 5"))

    assert result["type"] == "confirmation_required"
    assert result["pending"] == [
        {
            "tool_use_id": "tu1",
            "tool_name": "delete_recipe",
            "tool_input": {"recipe_id": 5},
        }
    ]
    assert calls == []  # not executed yet


def test_confirm_executes_the_pending_tool(monkeypatch):
    calls = []

    async def fake_delete_recipe(recipe_id):
        calls.append(recipe_id)
        return {"deleted_recipe_id": recipe_id}

    monkeypatch.setattr(
        dispatch, "TOOL_FUNCTIONS", {"delete_recipe": fake_delete_recipe}
    )
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset({"delete_recipe"}))

    fake = _install_fake_client(
        monkeypatch,
        [
            FakeMessage(
                [FakeToolUseBlock("tu1", "delete_recipe", {"recipe_id": 5})], "tool_use"
            ),
            FakeMessage([FakeTextBlock("Deleted recipe 5.")], "end_turn"),
        ],
    )

    session = _new_session()
    asyncio.run(agent.handle_user_message(session, "delete recipe 5"))
    result = asyncio.run(agent.handle_confirmation(session, "tu1", "confirm"))

    assert result == {"type": "message", "text": "Deleted recipe 5."}
    assert calls == [5]
    assert len(fake.messages.calls) == 2


def test_cancel_declines_and_never_executes(monkeypatch):
    calls = []

    async def fake_delete_recipe(recipe_id):
        calls.append(recipe_id)
        return {"deleted_recipe_id": recipe_id}

    monkeypatch.setattr(
        dispatch, "TOOL_FUNCTIONS", {"delete_recipe": fake_delete_recipe}
    )
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset({"delete_recipe"}))

    _install_fake_client(
        monkeypatch,
        [
            FakeMessage(
                [FakeToolUseBlock("tu1", "delete_recipe", {"recipe_id": 5})], "tool_use"
            ),
            FakeMessage([FakeTextBlock("Okay, not deleting it.")], "end_turn"),
        ],
    )

    session = _new_session()
    asyncio.run(agent.handle_user_message(session, "delete recipe 5"))
    result = asyncio.run(agent.handle_confirmation(session, "tu1", "cancel"))

    assert result == {"type": "message", "text": "Okay, not deleting it."}
    assert calls == []  # never executed


def test_unknown_confirmation_id_raises(monkeypatch):
    monkeypatch.setattr(dispatch, "TOOL_FUNCTIONS", {})
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset())
    session = _new_session()
    with pytest.raises(agent.UnknownConfirmationError):
        asyncio.run(agent.handle_confirmation(session, "nope", "confirm"))


def test_message_while_confirmation_pending_raises_conflict(monkeypatch):
    monkeypatch.setattr(dispatch, "TOOL_FUNCTIONS", {"delete_recipe": lambda **kw: {}})
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset({"delete_recipe"}))
    _install_fake_client(
        monkeypatch,
        [
            FakeMessage(
                [FakeToolUseBlock("tu1", "delete_recipe", {"recipe_id": 1})], "tool_use"
            )
        ],
    )
    session = _new_session()
    asyncio.run(agent.handle_user_message(session, "delete it"))
    with pytest.raises(agent.ConflictError):
        asyncio.run(agent.handle_user_message(session, "another message"))


def test_loop_stops_at_max_tool_rounds(monkeypatch):
    async def fake_search_recipes(**kwargs):
        return {"recipes": []}

    monkeypatch.setattr(
        dispatch, "TOOL_FUNCTIONS", {"search_recipes": fake_search_recipes}
    )
    monkeypatch.setattr(dispatch, "DESTRUCTIVE_TOOLS", frozenset())

    always_tool_use = [
        FakeMessage([FakeToolUseBlock(f"tu{i}", "search_recipes", {})], "tool_use")
        for i in range(10)
    ]
    fake = _install_fake_client(monkeypatch, always_tool_use)

    session = _new_session()
    result = asyncio.run(agent.handle_user_message(session, "search forever"))

    assert result["truncated"] is True
    assert len(fake.messages.calls) == get_settings().chat_max_tool_rounds
