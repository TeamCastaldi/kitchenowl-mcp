from fastmcp import FastMCP

_CACHED_TOOLS: list[dict] | None = None


async def prime_tool_schema_cache(server: FastMCP) -> None:
    """Build Anthropic tool defs from the tools FastMCP already registered.

    Called once at startup so the chat agent's tool list can never drift
    from what /mcp actually exposes — no hand-duplicated schemas.
    """
    global _CACHED_TOOLS
    tools = await server.list_tools()
    _CACHED_TOOLS = [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.parameters,
        }
        for tool in tools
    ]


def get_anthropic_tools() -> list[dict]:
    if _CACHED_TOOLS is None:
        raise RuntimeError(
            "tool schema cache not primed — call prime_tool_schema_cache() in lifespan"
        )
    return _CACHED_TOOLS
