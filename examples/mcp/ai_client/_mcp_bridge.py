"""Shared MCP client plumbing for the younit AI-client demos.

Not a demo itself — imported by openai_demo.py, azure_openai_demo.py, and
anthropic_demo.py to spawn the younit MCP server, list its tools in each
provider's function-calling format, and execute tool calls the LLM decides
to make.

SAFETY: connect_to_server() ALWAYS spawns the server subprocess with
EFG_MCP_READONLY=true, no matter what the caller's own environment has set.
This is hardcoded here — not exposed as a parameter — specifically so that
an LLM driving one of these demos can never place, amend, or cancel a real
order, regardless of how it reasons about the conversation. These demos are
for showing an LLM discover and call read-only market/portfolio tools; they
are not a safe place to exercise the write tools. To try the write tools,
run examples/mcp/server.py directly (see examples/mcp/claude_desktop_setup.md).
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

_SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "server.py"


@asynccontextmanager
async def connect_to_server() -> AsyncIterator[ClientSession]:
    """Spawn examples/mcp/server.py over stdio and yield a connected, initialised session.

    Tears down the subprocess and stdio streams on exit — normal return,
    exception, or KeyboardInterrupt all unwind through the two nested
    `async with` blocks below.

    If the subprocess dies (or the handshake otherwise fails) before a session
    is established, its captured stderr is attached to the raised exception so
    the real crash reason is visible instead of a bare "Connection closed".
    """
    env = {**os.environ, "EFG_MCP_READONLY": "true"}  # hard safety default, see module docstring
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER_SCRIPT), "--transport", "stdio"],
        env=env,
    )
    connected = False
    # Binary mode: the child writes raw bytes straight to this fd, and on Windows
    # those bytes aren't guaranteed to be UTF-8 — decode leniently below instead.
    with tempfile.TemporaryFile(mode="w+b") as stderr_capture:
        try:
            async with stdio_client(params, errlog=stderr_capture) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    connected = True
                    yield session
        except Exception as exc:
            if connected:
                raise  # failure happened after a working session was already handed to the caller
            stderr_capture.seek(0)
            captured = stderr_capture.read().decode("utf-8", errors="replace").strip()
            if captured:
                raise RuntimeError(
                    f"younit MCP server subprocess failed to start: {exc}\n"
                    f"--- captured server stderr ---\n{captured}"
                ) from exc
            raise


async def list_tools(session: ClientSession) -> list[types.Tool]:
    """List every tool the connected MCP server currently exposes."""
    result = await session.list_tools()
    return result.tools


def to_openai_tools(tools: list[types.Tool]) -> list[dict[str, Any]]:
    """Convert MCP tools to the OpenAI / Azure OpenAI `tools` parameter format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in tools
    ]


def to_anthropic_tools(tools: list[types.Tool]) -> list[dict[str, Any]]:
    """Convert MCP tools to the Anthropic Messages API `tools` parameter format."""
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }
        for tool in tools
    ]


async def call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> str:
    """Execute one tool call against the connected MCP server.

    Always returns a string — including on failure. Errors are turned into
    "ERROR: ..." text rather than raised, so callers can feed the result
    straight back to the LLM as the tool's reply and let it react, instead
    of the demo crashing mid-conversation.
    """
    try:
        result = await session.call_tool(name, arguments)
    except Exception as exc:  # transport/protocol failure, not a tool-level error
        return f"ERROR: MCP call to '{name}' failed: {exc}"

    text = "\n".join(block.text for block in result.content if isinstance(block, types.TextContent))
    if result.isError:
        return f"ERROR: {text or 'tool reported an error with no message'}"
    return text or "(tool returned no content)"
