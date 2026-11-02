"""Safety controls for the Younit MCP server.

All safety settings are configured via environment variables or a ``.env`` file
in the server's working directory (environment variables take precedence), the
same sources the SDK uses for ``TRADING_ID`` and ``API_KEY``.
No CLI flags. The user sets them once when configuring
their MCP server (in claude_desktop_config.json, systemd unit, .env, etc.) and
they apply to every subsequent operation.

Safety settings:
- ``EFG_MCP_READONLY``: Write tools are registered ONLY when this is explicitly
  ``false``. Unset, empty, ``true`` or any other value keeps the server
  read-only: the LLM never sees buy/sell/cancel/amend tools.
- ``EFG_MCP_MAX_ORDER_VALUE_EGP``: Cap on qty*price for any single order.
  While the cap is active, market orders (no limit price) are rejected because
  their value cannot be bounded. Set to 0 to disable (not recommended in
  production).
- ``EFG_MCP_MAX_DAILY_ORDERS``: Circuit breaker on orders sent to the API per
  Africa/Cairo calendar day. The count is in memory only, so it also resets
  when the server restarts. Set to 0 to disable.

These limits apply only to the MCP server. SDK users bypass them intentionally.

The LLM never sees these limits as order parameters. A ``buy`` tool takes
``symbol``, ``qty``, ``limit`` — nothing else. The cap is a server property,
not an order property. The LLM can read the effective values with the
read-only ``get_safety_settings`` tool, and is told about a limit if it tries
to exceed it.
"""

from __future__ import annotations

import math
import re
import sys
import threading
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CAIRO_TZ = ZoneInfo("Africa/Cairo")

_DEFAULT_MAX_ORDER_VALUE_EGP = 1_000
_DEFAULT_MAX_DAILY_ORDERS = 100

# Plain non-negative decimal: whole part, optional fractional digits (ASCII only).
_NUMBER = re.compile(r"([0-9]+)(?:\.([0-9]+))?", re.ASCII)


class _RawSafetySource(BaseSettings):
    """Raw EFG_MCP_* strings from the environment, then ``.env`` in the cwd.

    Same sources and precedence as :class:`younit.config.Settings` (environment
    variables win over ``.env``), without loading ``.env`` into ``os.environ``.
    Values stay strings so that a malformed value can never raise here; they
    are interpreted fail-safe by :class:`SafetySettings`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    readonly: str | None = Field(default=None, validation_alias="EFG_MCP_READONLY")
    max_order_value_egp: str | None = Field(
        default=None, validation_alias="EFG_MCP_MAX_ORDER_VALUE_EGP"
    )
    max_daily_orders: str | None = Field(default=None, validation_alias="EFG_MCP_MAX_DAILY_ORDERS")


def _load_raw() -> _RawSafetySource:
    """Load the raw settings; if the sources are unreadable, use the safe defaults."""
    try:
        return _RawSafetySource()
    except Exception as exc:  # any load failure must fail safe, never crash open
        print(
            f"Could not read EFG_MCP_* safety settings ({type(exc).__name__}); "
            "using the safe defaults (read-only).",
            file=sys.stderr,
        )
        return _RawSafetySource.model_construct()


def _limit(raw: str | None, default: int) -> int:
    """Parse a non-negative limit; 0 disables it.

    Accepts whole numbers written as "250", " 250 " or "250.0". A fractional
    value is rounded DOWN (stricter): "250.9" is 250. Unset, empty, malformed or
    negative values fall back to the default limit, never to "disabled". A
    positive value that would round down to 0 ("0.5") also falls back to the
    default, because 0 would turn the limit off.
    """
    if raw is None:
        return default
    match = _NUMBER.fullmatch(raw.strip())
    if match is None:
        return default
    whole = int(match.group(1))
    if whole == 0 and match.group(2) and int(match.group(2)) != 0:
        return default
    return whole


class SafetySettings:
    """Safety configuration for the MCP server.

    Read from environment variables first, then from ``.env`` in the working
    directory (like the SDK's ``Settings``).

    Attributes:
        readonly: If True (the default), all write tools (buy, sell, cancel,
            amend) are not registered with the MCP server. Only an explicit
            ``EFG_MCP_READONLY=false`` sets this to False.
        max_order_value_egp: Maximum allowed order value (qty * price) in EGP.
            Zero means no limit.
        max_daily_orders: Maximum number of orders per Africa/Cairo calendar
            day. Zero means no limit.
    """

    def __init__(self) -> None:
        raw = _load_raw()
        self.readonly: bool = (raw.readonly or "").strip().lower() != "false"
        self.max_order_value_egp: int = _limit(
            raw.max_order_value_egp, _DEFAULT_MAX_ORDER_VALUE_EGP
        )
        self.max_daily_orders: int = _limit(raw.max_daily_orders, _DEFAULT_MAX_DAILY_ORDERS)


class DailyOrderCounter:
    """Counts orders sent to the API in the current Africa/Cairo calendar day.

    Memory only: nothing is persisted, so the count also resets whenever the
    server restarts. Thread-safe: :meth:`reserve` checks the limit and counts
    the order atomically.

    Args:
        clock: Returns the current time as a timezone-aware datetime. Defaults
            to the real clock; override in tests.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(CAIRO_TZ))
        self._lock = threading.Lock()
        self._count = 0
        self._date: date = self._today()

    def _today(self) -> date:
        return self._clock().astimezone(CAIRO_TZ).date()

    def _maybe_reset(self) -> None:
        today = self._today()
        if today != self._date:
            self._count = 0
            self._date = today

    def increment(self) -> int:
        """Increment the counter and return the new count."""
        with self._lock:
            self._maybe_reset()
            self._count += 1
            return self._count

    def reserve(self, settings: SafetySettings) -> int:
        """Check the daily limit and count one order, in a single atomic step.

        Call this after every other safety check has passed and immediately
        before sending the order. The order stays counted even if the API call
        then fails.

        Returns:
            The new count for today.

        Raises:
            ValueError: If the daily limit has been reached (nothing is counted).
        """
        with self._lock:
            self._maybe_reset()
            if 0 < settings.max_daily_orders <= self._count:
                raise ValueError(_daily_limit_message(settings.max_daily_orders))
            self._count += 1
            return self._count

    @property
    def count(self) -> int:
        """Current order count for today."""
        with self._lock:
            self._maybe_reset()
            return self._count


def _daily_limit_message(limit: int) -> str:
    return (
        f"Daily order limit of {limit} orders has been reached for today "
        f"(Cairo time). No more orders can be placed via the MCP server today. "
        f"This limit resets at midnight Cairo time or when the server restarts."
    )


def check_order_value(
    qty: int,
    price: float | None,
    settings: SafetySettings,
) -> None:
    """Raise if the order value exceeds the configured cap.

    While the cap is active, an order with no limit price (a market order) is
    rejected: its execution price is unknown at placement time, so its value
    cannot be bounded.

    Args:
        qty: Number of shares.
        price: Limit price in EGP, or None for market orders.
        settings: Active safety settings.

    Raises:
        ValueError: With a clear message the LLM can relay to the user.
    """
    if settings.max_order_value_egp <= 0:
        return  # Disabled

    cap = settings.max_order_value_egp
    if price is None:
        raise ValueError(
            f"Market orders (no limit price) are not allowed while the MCP server "
            f"safety cap of {cap:,.2f} EGP is active, because their value cannot be "
            f"verified. Ask the user for a limit price and retry with one, or "
            f"use the SDK directly."
        )
    if not (math.isfinite(price) and price > 0 and qty > 0):
        raise ValueError(
            f"Invalid order: quantity ({qty}) and limit price ({price}) must both be "
            f"positive numbers."
        )

    value = qty * price
    if value > cap:
        raise ValueError(
            f"Order value {value:,.2f} EGP exceeds the MCP server safety cap "
            f"of {cap:,.2f} EGP. To place larger orders, use the SDK directly "
            f"or increase EFG_MCP_MAX_ORDER_VALUE_EGP."
        )


def check_daily_limit(counter: DailyOrderCounter, settings: SafetySettings) -> None:
    """Raise if the daily order limit has been reached.

    Args:
        counter: The daily order counter instance.
        settings: Active safety settings.

    Raises:
        ValueError: With a clear message the LLM can relay to the user.
    """
    if settings.max_daily_orders <= 0:
        return  # Disabled

    if counter.count >= settings.max_daily_orders:
        raise ValueError(_daily_limit_message(settings.max_daily_orders))
