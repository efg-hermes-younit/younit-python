"""The MCP server must stay up and report a clear error when startup auth fails."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import conftest as conf
import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from younit.exceptions import APIError, ConfigError
from younit.mcp_server import server

AUTH_MESSAGE = "Authentication failed: check your Trading ID and API key."
HTML_PAGE = "<html><body>Blocked by firewall</body></html>"


@pytest.fixture
def run_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Run main() with a clean module state and a recording app.run."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setenv("TRADING_ID", conf.FAKE_TRADING_ID)
    monkeypatch.setenv("API_KEY", conf.FAKE_API_KEY)
    monkeypatch.setenv("EFG_MCP_READONLY", "true")
    monkeypatch.setattr(sys, "argv", ["younit-mcp"])
    monkeypatch.setattr(server, "_client", None)
    monkeypatch.setattr(server, "_safety", None)
    monkeypatch.setattr(server, "_startup_error", None)
    monkeypatch.setattr(server.app, "run", lambda **kwargs: calls.append(kwargs))
    return calls


def _call_quote() -> None:
    asyncio.run(server.app.call_tool("quote", {"symbol": "COMI"}))


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(httpx.Response(400, json={"message": "Bad request"}), id="http-400"),
        pytest.param(httpx.Response(401, json={"message": "Unauthorized"}), id="http-401"),
        pytest.param(httpx.Response(200, text=HTML_PAGE), id="http-200-html"),
        pytest.param(httpx.Response(403, text=HTML_PAGE), id="http-403-html"),
    ],
)
def test_startup_auth_failure_keeps_server_up(
    respx_mock: respx.MockRouter,
    run_calls: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
    response: httpx.Response,
) -> None:
    respx_mock.post(conf.TOKEN_URL).mock(return_value=response)

    server.main()

    assert run_calls == [{"transport": "stdio"}]
    with pytest.raises(ToolError) as caught:
        _call_quote()
    assert AUTH_MESSAGE in str(caught.value)

    captured = capsys.readouterr()
    assert captured.out == ""
    for text in (str(caught.value), captured.err):
        assert conf.FAKE_TRADING_ID not in text
        assert conf.FAKE_API_KEY not in text


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(
            ConfigError("Invalid configuration: trading_id: Field required"),
            "Server failed to start: Invalid configuration",
            id="config",
        ),
        pytest.param(
            APIError("boom", status_code=500), "Server failed to start (APIError)", id="api"
        ),
    ],
)
def test_other_startup_errors_keep_server_up(
    monkeypatch: pytest.MonkeyPatch,
    run_calls: list[dict[str, Any]],
    error: Exception,
    expected: str,
) -> None:
    def _raise() -> None:
        raise error

    monkeypatch.setattr(server, "Client", _raise)

    server.main()

    assert run_calls == [{"transport": "stdio"}]
    with pytest.raises(ToolError) as caught:
        _call_quote()
    assert expected in str(caught.value)
