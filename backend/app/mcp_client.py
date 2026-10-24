"""Thin MCP client used by the backend to discover and call the contract tools.

The agent loop (next step) uses `mcp_session()` to list the server's tools,
hands their schemas to the LLM, and executes the calls the LLM asks for.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from . import config


class MCPUnavailable(RuntimeError):
    """The MCP server could not be reached."""


@asynccontextmanager
async def mcp_session(url: str | None = None) -> AsyncIterator[ClientSession]:
    """Open an initialised MCP session for the duration of a `async with` block."""
    target = url or config.MCP_SERVER_URL
    try:
        async with streamable_http_client(target) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    except Exception as exc:
        cause = _connection_error(exc)
        if cause is None:
            raise
        raise MCPUnavailable(f"Cannot reach the MCP server at {target} ({type(cause).__name__})") from None


def _connection_error(exc: BaseException) -> BaseException | None:
    """Find a connection failure, which anyio may wrap in (nested) exception groups."""
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return exc
    for inner in getattr(exc, "exceptions", None) or ():
        found = _connection_error(inner)
        if found is not None:
            return found
    return None


def result_payload(result: CallToolResult) -> Any:
    """The tool's output as plain data: structured content if present, else the text parts."""
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [c.text for c in result.content if isinstance(c, TextContent)]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except (ValueError, TypeError):
        return joined
