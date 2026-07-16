import json
import logging

import anthropic

from ..config import get_settings
from . import dispatch, tool_schemas
from .sessions import ChatSession, PendingConfirmation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a household assistant with access to this family's KitchenOwl "
    "instance: recipes, shopping list, and meal plan. Use the available "
    "tools to answer questions and make changes. Be concise. When you list "
    "more than one recipe (or other item), use a numbered markdown list "
    "starting at 1 and incrementing by 1 through the last item — never "
    "repeat '1.' for every entry. If the user later refers to an item by "
    "its number (e.g. 'tell me more about #2' or 'add 3 to the meal "
    "plan'), resolve it against the most recent numbered list you sent."
)


class ConflictError(Exception):
    pass


class UnknownConfirmationError(Exception):
    pass


_anthropic_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=get_settings().anthropic_api_key
        )
    return _anthropic_client


async def handle_user_message(session: ChatSession, user_text: str) -> dict:
    if session.pending_tool_uses:
        raise ConflictError("resolve the pending confirmation first")
    session.messages.append({"role": "user", "content": user_text})
    return await _run_loop(session)


async def handle_confirmation(
    session: ChatSession, tool_use_id: str, decision: str
) -> dict:
    pending = _pop_pending(session, tool_use_id)
    if decision == "confirm":
        result = await _execute_tool(pending.tool_name, pending.tool_input)
    else:
        result = {"declined_by_user": True}
    session.pending_ready_results.append(
        _tool_result_block(pending.tool_use_id, result)
    )

    if session.pending_tool_uses:
        return _confirmation_payload(session)

    session.messages.append({"role": "user", "content": session.pending_ready_results})
    session.pending_ready_results = []
    return await _run_loop(session)


def _pop_pending(session: ChatSession, tool_use_id: str) -> PendingConfirmation:
    for i, p in enumerate(session.pending_tool_uses):
        if p.tool_use_id == tool_use_id:
            return session.pending_tool_uses.pop(i)
    raise UnknownConfirmationError(f"no pending confirmation for {tool_use_id!r}")


async def _run_loop(session: ChatSession) -> dict:
    settings = get_settings()
    client = _get_anthropic_client()

    for _ in range(settings.chat_max_tool_rounds):
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.chat_max_tokens,
            system=SYSTEM_PROMPT,
            tools=tool_schemas.get_anthropic_tools(),
            messages=session.messages,
        )
        session.messages.append(
            {"role": "assistant", "content": [b.model_dump() for b in response.content]}
        )

        if response.stop_reason != "tool_use":
            return {"type": "message", "text": _extract_text(response)}

        results = []
        pending = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name in dispatch.DESTRUCTIVE_TOOLS:
                pending.append(PendingConfirmation(block.id, block.name, block.input))
            else:
                result = await _execute_tool(block.name, block.input)
                results.append(_tool_result_block(block.id, result))

        if pending:
            session.pending_tool_uses = pending
            session.pending_ready_results = results
            return _confirmation_payload(session)

        session.messages.append({"role": "user", "content": results})

    return {
        "type": "message",
        "text": "Stopped after too many tool calls — try rephrasing.",
        "truncated": True,
    }


async def _execute_tool(name: str, tool_input: dict) -> dict:
    fn = dispatch.TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        result = await fn(**tool_input)
    except Exception as e:
        logger.exception("chat tool %s failed", name)
        return {"error": str(e)}
    return result if isinstance(result, dict | list) else {"result": result}


def _tool_result_block(tool_use_id: str, result: dict | list) -> dict:
    is_error = isinstance(result, dict) and set(result) == {"error"}
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result),
        "is_error": is_error,
    }


def _confirmation_payload(session: ChatSession) -> dict:
    return {
        "type": "confirmation_required",
        "pending": [
            {
                "tool_use_id": p.tool_use_id,
                "tool_name": p.tool_name,
                "tool_input": p.tool_input,
            }
            for p in session.pending_tool_uses
        ],
    }


def _extract_text(response) -> str:
    return "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
