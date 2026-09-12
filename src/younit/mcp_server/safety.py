"""Safety controls for the Younit MCP server.

All safety settings are configured via environment variables ONLY.
No CLI flags. No config files. The user sets them once when configuring
their MCP server (in claude_desktop_config.json, systemd unit, etc.) and
they apply to every subsequent operation.

Safety settings:
- ``EFG_MCP_READONLY``: If true, write tools are not registered at all.
  The LLM never sees buy/sell/cancel/amend tools.
- ``EFG_MCP_MAX_ORDER_VALUE_EGP``: Cap on qty*price for any single order.
  Set to 0 to disable (not recommended in production).
- ``EFG_MCP_MAX_DAILY_ORDERS``: Circuit breaker on orders per UTC day.
  Set to 0 to disable.

These limits apply only to the MCP server. SDK users bypass them intentionally.

The LLM never sees these limits as parameters. A ``buy`` tool takes
``symbol``, ``qty``, ``limit`` — nothing else. The cap is a server property,
not an order property. The LLM only learns about a limit if it tries to
exceed it and receives an error message in the tool response.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean env var."""
    val = os.environ.get(name, "").lower().strip()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no", ""):
        return default
    return default


def _env_int(name: str, default: int) -> int:
    """Read an integer env var."""
    val = os.environ.get(name, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


class SafetySettings:
    """Safety configuration for the MCP server, loaded from environment variables.

    Attributes:
        readonly: If True, all write tools (buy, sell, cancel, amend) are
            not registered with the MCP server.
        max_order_value_egp: Maximum allowed order value (qty * price) in EGP.
            Zero means no limit.
        max_daily_orders: Maximum number of orders per UTC calendar day.
            Zero means no limit.
    """

    def __init__(self) -> None:
        self.readonly: bool = _env_bool("EFG_MCP_READONLY", default=False)
        self.max_order_value_egp: int = _env_int("EFG_MCP_MAX_ORDER_VALUE_EGP", default=1_000)
        self.max_daily_orders: int = _env_int("EFG_MCP_MAX_DAILY_ORDERS", default=100)


class DailyOrderCounter:
    """Tracks the number of orders placed in the current UTC day.

    Resets at UTC midnight automatically.
    """

    def __init__(self) -> None:
        self._count = 0
        self._date: str = self._today()

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _maybe_reset(self) -> None:
        today = self._today()
        if today != self._date:
            self._count = 0
            self._date = today

    def increment(self) -> int:
        """Increment the counter and return the new count."""
        self._maybe_reset()
        self._count += 1
        return self._count

    @property
    def count(self) -> int:
        """Current order count for today."""
        self._maybe_reset()
        return self._count


def check_order_value(
    qty: int,
    price: float | None,
    settings: SafetySettings,
) -> None:
    """Raise if the order value exceeds the configured cap.

    For market orders (price=None), the check is skipped because the
    execution price is unknown at placement time.

    Args:
        qty: Number of shares.
        price: Limit price in EGP, or None for market orders.
        settings: Active safety settings.

    Raises:
        ValueError: With a clear message the LLM can relay to the user.
    """
    if settings.max_order_value_egp <= 0:
        return  # Disabled
    if price is None:
        return  # Market order — can't validate without execution price

    value = qty * price
    cap = settings.max_order_value_egp
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
        raise ValueError(
            f"Daily order limit of {settings.max_daily_orders} orders has been reached "
            f"for today (UTC). No more orders can be placed via the MCP server today. "
            f"This limit resets at UTC midnight."
        )
