"""Shared MCP client plumbing for the younit AI-client demos.

Not a demo itself — imported by openai_demo.py, azure_openai_demo.py, and
anthropic_demo.py to spawn the younit MCP server, list its tools in each
provider's function-calling format, and execute tool calls the LLM decides
to make.

SAFETY: whether the AI can trade is decided ONLY by the READ_ONLY constant below
(it defaults to True). The bridge sets EFG_MCP_READONLY for the server from that
constant alone ("true" or "false"); it never reads EFG_MCP_READONLY from the
environment or from .env, so a stray setting cannot turn trading on. The server
is always started with an explicit value, which also beats any .env it reads.
With READ_ONLY = False the AI can place, amend and cancel REAL orders, limited by
EFG_MCP_MAX_ORDER_VALUE_EGP and EFG_MCP_MAX_DAILY_ORDERS; a warning is printed
at startup.

ENVIRONMENT: the server does not inherit the demo's whole environment (that
would hand it the LLM provider keys). It receives only the variables in
``FORWARDED_ENV_VARS`` (plus proxy / CA-bundle variables) that are set and
non-empty, plus EFG_MCP_READONLY from READ_ONLY. Values are never printed. The
server runs with this directory as its working directory, so the ``.env`` it
reads itself is examples/mcp/ai_client/.env — the same file the demos load —
regardless of where you launched the demo from.

SIMULATION: simulation mode is temporarily disabled in this version. If
EFG_SIMULATION is set (after the demo has loaded ai_client/.env) to anything
other than empty, "false", "0" or "no", the demo prints the SDK's message to
stderr and exits with code 1 before starting the server. A set value is also
forwarded to the server, so the server's own check applies too.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# Safety switch for all AI client demos.
# True  = the AI can only read (quotes, portfolio, history...).
# False = the AI can place, amend and cancel REAL orders on your account.
READ_ONLY = True

_HERE = Path(__file__).resolve().parent
_SERVER_SCRIPT = _HERE.parent / "server.py"

TRADING_WARNING = (
    "WARNING: READ_ONLY is False in _mcp_bridge.py. The AI can place, amend and cancel "
    "REAL orders on your account. The per-order value cap (EFG_MCP_MAX_ORDER_VALUE_EGP) "
    "and the daily limit (EFG_MCP_MAX_DAILY_ORDERS) still apply."
)

# Same text as the SDK's ConfigError, so the demo fails the same way the server would.
SIMULATION_DISABLED_MESSAGE = (
    "EFG_SIMULATION is temporarily disabled in this version while simulation mode "
    "is being verified. Remove EFG_SIMULATION to continue."
)

# Values of EFG_SIMULATION that mean "off"; anything else stops the demo.
_SIMULATION_OFF_VALUES = frozenset({"", "false", "0", "no"})

# Passed to the server explicitly when set. EFG_MCP_READONLY is deliberately
# absent: it comes from READ_ONLY only, never from the environment or .env.
FORWARDED_ENV_VARS = (
    "TRADING_ID",
    "API_KEY",
    "EFG_LOG_LEVEL",
    "EFG_SIMULATION",
    "EFG_MCP_MAX_ORDER_VALUE_EGP",
    "EFG_MCP_MAX_DAILY_ORDERS",
)

# Network plumbing the server's HTTP client honours; without these the demo
# would stop working behind a proxy or a custom CA.
_NETWORK_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)


def build_server_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for the spawned MCP server: forwarded variables plus read-only mode."""
    source = os.environ if environ is None else environ
    names = FORWARDED_ENV_VARS + _NETWORK_ENV_VARS
    env = {name: source[name] for name in names if source.get(name, "").strip()}
    env["EFG_MCP_READONLY"] = "true" if READ_ONLY else "false"  # from READ_ONLY only
    return env


def mode_note_for_system_prompt() -> str:
    """One sentence telling the LLM whether trading is enabled."""
    if READ_ONLY:
        return (
            "The server is running in read-only mode: you cannot place, amend, "
            "or cancel real orders."
        )
    return (
        "Trading is enabled: placing, amending or cancelling an order affects the "
        "user's REAL account. Only do so when the user explicitly asks you to."
    )


def exit_if_simulation_requested(environ: Mapping[str, str] | None = None) -> None:
    """Exit with code 1 if EFG_SIMULATION is set to anything but empty/false/0/no.

    Checked before the server is started, after the demo has loaded ai_client/.env.
    """
    source = os.environ if environ is None else environ
    if source.get("EFG_SIMULATION", "").strip().lower() not in _SIMULATION_OFF_VALUES:
        print(SIMULATION_DISABLED_MESSAGE, file=sys.stderr, flush=True)
        sys.exit(1)


def warn_if_trading_enabled() -> None:
    """Print the trading warning (to stderr) when READ_ONLY is False."""
    if not READ_ONLY:
        print(TRADING_WARNING, file=sys.stderr, flush=True)


def server_parameters() -> StdioServerParameters:
    """How the demos launch examples/mcp/server.py over stdio."""
    return StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER_SCRIPT), "--transport", "stdio"],
        env=build_server_env(),
        cwd=_HERE,
    )


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
    exit_if_simulation_requested()
    warn_if_trading_enabled()
    params = server_parameters()
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
