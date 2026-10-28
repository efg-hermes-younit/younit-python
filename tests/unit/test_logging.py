"""Logging must never write to stdout (reserved for MCP stdio JSON-RPC)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import conftest as conf
import pytest
import structlog

from younit.client import Client
from younit.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    structlog.reset_defaults()


@pytest.mark.usefixtures("auth_routes")
def test_client_startup_logs_only_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EFG_LOG_LEVEL", "INFO")
    monkeypatch.setenv("EFG_DEBUG", "false")

    Client(trading_id=conf.FAKE_TRADING_ID, api_key=conf.FAKE_API_KEY, lazy_symbols=True)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fetching_token" in captured.err


def test_stdlib_and_structlog_records_go_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO")

    get_logger("younit.test").info("structlog_event")
    logging.getLogger("httpx").info("stdlib_event")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "structlog_event" in captured.err
    assert "stdlib_event" in captured.err


def test_debug_mode_logs_only_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", debug=True)

    get_logger("younit.test").debug("debug_event")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "debug_event" in captured.err


def test_log_level_is_still_respected(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="WARNING")

    log = get_logger("younit.test")
    log.info("hidden_event")
    log.warning("shown_event")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hidden_event" not in captured.err
    assert "shown_event" in captured.err
