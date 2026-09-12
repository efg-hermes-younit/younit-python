"""Pydantic models for real-time streaming updates from Lightstreamer.

Five stream types are available (documented in the streaming guide):
- SymbolStatistics  — live price, bid/ask, volume per stock
- IndexStatistics   — live index value per index
- MarketStatistics  — market aggregates per market
- SecurityTrades    — individual trade tape per stock
- ActiveOrders      — client's live order lifecycle updates

All field names are normalised from the raw Lightstreamer format
(e.g. ``m_LastTradePrice``) to idiomatic Python snake_case.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Subscription handle
# ---------------------------------------------------------------------------


@dataclass
class Subscription:
    """An active Lightstreamer subscription.

    Returned by all ``subscribe_*`` methods.  Pass to
    ``client.streaming.unsubscribe()`` to cancel the subscription.

    Attributes:
        stream_type: Human-readable stream name (e.g. ``"SymbolStatistics"``).
        item: Lightstreamer item name (e.g. ``"sy12345"``).
        on_update: The user callback registered for this subscription.
        _ls_subscription: Internal Lightstreamer subscription object. Do not
            use directly unless you need raw Lightstreamer control. May also
            be a ``list[Subscription]`` for composite handles that aggregate
            several underlying subscriptions (e.g.
            :meth:`~younit.client.Client.stream_top_movers`) —
            ``StreamingClient.unsubscribe`` tears down each one in turn.
    """

    stream_type: str
    item: str
    on_update: Callable[..., None]
    on_error: Callable[[Exception], None] | None = None
    _ls_subscription: Any = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# SymbolStatistics update model
# ---------------------------------------------------------------------------


class SymbolUpdate:
    """A live price update for a single stock from the SymbolStatistics stream.

    Fields are populated from the Lightstreamer update.  Any field that was
    not included in the update will be ``None`` (Lightstreamer only sends
    changed fields after the initial snapshot).

    Attributes:
        stock_id: Internal stock identifier.
        symbol: EGX ticker symbol.
        name: Company name.
        last: Last traded price in EGP.
        open: Opening price in EGP.
        close: Previous close price in EGP.
        high: Intraday high in EGP.
        low: Intraday low in EGP.
        bid: Best bid price in EGP.
        bid_volume: Best bid volume (shares).
        ask: Best ask price in EGP.
        ask_volume: Best ask volume (shares).
        volume: Total traded volume (shares).
        value: Total traded value in EGP.
        trades_count: Number of executed trades today.
        change: Price change from previous close in EGP.
        change_pct: Price change as a percentage.
        reference_price: Reference (base) price in EGP.
        week52_high: 52-week high price in EGP.
        week52_low: 52-week low price in EGP.
        market_cap: Market capitalisation in EGP.
        status_id: Numeric symbol status code.
        status: Human-readable symbol status.
        last_updated: Timestamp string of last update.
        raw: Full raw field dict from Lightstreamer for advanced use.
    """

    __slots__ = (
        "ask",
        "ask_volume",
        "bid",
        "bid_volume",
        "change",
        "change_pct",
        "close",
        "high",
        "last",
        "last_updated",
        "low",
        "market_cap",
        "name",
        "open",
        "raw",
        "reference_price",
        "status",
        "status_id",
        "stock_id",
        "symbol",
        "trades_count",
        "value",
        "volume",
        "week52_high",
        "week52_low",
    )

    def __init__(self, raw: dict[str, str | None]) -> None:
        self.raw = raw
        self.stock_id: int | None = _int(raw.get("m_SymbolID"))
        self.symbol: str | None = raw.get("m_ShortName")
        self.name: str | None = raw.get("m_StockName")
        self.last: float | None = _float(raw.get("m_LastTradePrice"))
        self.open: float | None = _float(raw.get("m_OpenPrice"))
        self.close: float | None = _float(raw.get("m_ClosePrice"))
        self.high: float | None = _float(raw.get("m_DailyHighPrice"))
        self.low: float | None = _float(raw.get("m_DailyLowPrice"))
        self.bid: float | None = _float(raw.get("m_BidPrice"))
        self.bid_volume: int | None = _int(raw.get("m_BidVol"))
        self.ask: float | None = _float(raw.get("m_AskPrice"))
        self.ask_volume: int | None = _int(raw.get("m_AskVol"))
        self.volume: int | None = _int(raw.get("m_TradedVolume"))
        self.value: float | None = _float(raw.get("m_TradedValue"))
        self.trades_count: int | None = _int(raw.get("m_TradesCount"))
        self.change: float | None = _float(raw.get("m_Change"))
        self.change_pct: float | None = _float(raw.get("m_PercentChange"))
        self.reference_price: float | None = _float(raw.get("m_ReferencePrice"))
        self.week52_high: float | None = _float(raw.get("m_Wk52HighPrice"))
        self.week52_low: float | None = _float(raw.get("m_Wk52LowPrice"))
        self.market_cap: float | None = _float(raw.get("m_MarketCap"))
        self.status_id: int | None = _int(raw.get("m_SymbolStatusID"))
        self.status: str | None = raw.get("m_SymbolStatusUI")
        self.last_updated: str | None = raw.get("m_LastUpdated")

    def __repr__(self) -> str:
        return (
            f"SymbolUpdate(symbol={self.symbol!r}, last={self.last}, change_pct={self.change_pct})"
        )


# ---------------------------------------------------------------------------
# stream_top_movers() ranked-entry model
# ---------------------------------------------------------------------------


@dataclass
class TopMover:
    """A single ranked entry in a :meth:`~younit.client.Client.stream_top_movers` update.

    Built client-side from the latest :class:`SymbolUpdate` seen for a watched
    symbol — not a distinct API response shape.

    Attributes:
        stock_id: Internal stock identifier.
        symbol: EGX ticker symbol.
        name: Company name.
        last: Last traded price in EGP.
        change: Price change from previous close in EGP.
        change_pct: Price change as a percentage.
    """

    stock_id: int | None
    symbol: str
    name: str | None
    last: float | None
    change: float | None
    change_pct: float | None


# ---------------------------------------------------------------------------
# IndexStatistics update model
# ---------------------------------------------------------------------------


class IndexUpdate:
    """A live value update for a market index from the IndexStatistics stream.

    Attributes:
        index_id: Internal index identifier.
        name: Index name in English.
        value: Current index value.
        open: Opening index value.
        close: Previous close value.
        high: Intraday high.
        low: Intraday low.
        week52_high: 52-week high.
        week52_low: 52-week low.
        net_change: Net change from previous close.
        change_pct: Percentage change (note: field is ``m_PrecentChange`` in raw data).
        traded_value: Total traded value in EGP.
        traded_volume: Total traded volume.
        raw: Full raw field dict.
    """

    __slots__ = (
        "change_pct",
        "close",
        "high",
        "index_id",
        "low",
        "name",
        "net_change",
        "open",
        "raw",
        "traded_value",
        "traded_volume",
        "value",
        "week52_high",
        "week52_low",
    )

    def __init__(self, raw: dict[str, str | None]) -> None:
        self.raw = raw
        self.index_id: int | None = _int(raw.get("m_IndexID"))
        self.name: str | None = raw.get("m_EnglishName")
        self.value: float | None = _float(raw.get("m_IndexValue"))
        self.open: float | None = _float(raw.get("m_IndexOpen"))
        self.close: float | None = _float(raw.get("m_IndexClose"))
        self.high: float | None = _float(raw.get("m_IndexHigh"))
        self.low: float | None = _float(raw.get("m_IndexLow"))
        self.week52_high: float | None = _float(raw.get("m_IndexWk52High"))
        self.week52_low: float | None = _float(raw.get("m_IndexWk52Low"))
        self.net_change: float | None = _float(raw.get("m_NetChange"))
        # Note: typo in the API field name — "m_PrecentChange" not "m_PercentChange"
        self.change_pct: float | None = _float(raw.get("m_PrecentChange"))
        self.traded_value: float | None = _float(raw.get("m_TradedValue"))
        self.traded_volume: float | None = _float(raw.get("m_TradedVolume"))

    def __repr__(self) -> str:
        return f"IndexUpdate(index_id={self.index_id}, name={self.name!r}, value={self.value})"


# ---------------------------------------------------------------------------
# MarketStatistics update model
# ---------------------------------------------------------------------------


class MarketUpdate:
    """Aggregated statistics for an entire market from the MarketStatistics stream.

    Attributes:
        market_id: Internal market identifier (1 = EGX).
        name: Market name in English.
        status: Market status string (e.g. ``"Open"``, ``"Closed"``).
        traded_value: Total market traded value in EGP.
        traded_volume: Total market traded volume (shares).
        trades_count: Total number of trades executed today.
        symbols_traded: Number of symbols with at least one trade today.
        advances: Number of advancing (gaining) symbols.
        declines: Number of declining symbols.
        unchanged: Number of unchanged symbols.
        market_time: Current market time string.
        open_time: Market open time string.
        close_time: Market close time string.
        raw: Full raw field dict.
    """

    __slots__ = (
        "advances",
        "close_time",
        "declines",
        "market_id",
        "market_time",
        "name",
        "open_time",
        "raw",
        "status",
        "symbols_traded",
        "traded_value",
        "traded_volume",
        "trades_count",
        "unchanged",
    )

    def __init__(self, raw: dict[str, str | None]) -> None:
        self.raw = raw
        self.market_id: int | None = _int(raw.get("m_MarketID"))
        self.name: str | None = raw.get("m_EnglishName")
        self.status: str | None = raw.get("m_MarketStatus")
        self.traded_value: float | None = _float(raw.get("m_TradedValue"))
        self.traded_volume: float | None = _float(raw.get("m_TradedVolume"))
        self.trades_count: int | None = _int(raw.get("m_TradesCount"))
        self.symbols_traded: int | None = _int(raw.get("m_TradedSymCount"))
        self.advances: int | None = _int(raw.get("m_AdvTradesCount"))
        self.declines: int | None = _int(raw.get("m_DclnTradesCount"))
        self.unchanged: int | None = _int(raw.get("m_UnchgTradesCount"))
        self.market_time: str | None = raw.get("MarketTime")
        self.open_time: str | None = raw.get("m_OpenTime")
        self.close_time: str | None = raw.get("m_CloseTime")

    def __repr__(self) -> str:
        return (
            f"MarketUpdate(market_id={self.market_id}, status={self.status!r}, "
            f"traded_value={self.traded_value})"
        )


# ---------------------------------------------------------------------------
# SecurityTrades update model (COMMAND mode)
# ---------------------------------------------------------------------------


class TradeUpdate:
    """A single executed trade from the SecurityTrades stream (COMMAND mode).

    Lightstreamer COMMAND mode delivers individual ADD/UPDATE/DELETE events.
    Each event corresponds to one executed trade in the tape.

    Attributes:
        command: Lightstreamer command: ``"ADD"``, ``"UPDATE"``, or ``"DELETE"``.
        key: Lightstreamer row key (unique per trade entry).
        stock_id: Internal stock identifier.
        ticket_number: Exchange trade ticket number.
        price: Executed trade price in EGP.
        volume: Number of shares in this trade.
        last_updated: Timestamp string.
        change_from_close: Price change vs previous close in EGP.
        change_pct_from_close: Percentage change vs previous close.
        transaction_type: Buy/sell side indicator.
        raw: Full raw field dict.
    """

    __slots__ = (
        "change_from_close",
        "change_pct_from_close",
        "command",
        "key",
        "last_updated",
        "price",
        "raw",
        "stock_id",
        "ticket_number",
        "transaction_type",
        "volume",
    )

    def __init__(self, raw: dict[str, str | None]) -> None:
        self.raw = raw
        self.command: str | None = raw.get("command")
        self.key: str | None = raw.get("key")
        self.stock_id: int | None = _int(raw.get("m_SymbolID"))
        self.ticket_number: str | None = raw.get("m_TicketNumber")
        self.price: float | None = _float(raw.get("m_TradePrice"))
        self.volume: int | None = _int(raw.get("m_TradeVolume"))
        self.last_updated: str | None = raw.get("m_LastUpdated")
        self.change_from_close: float | None = _float(raw.get("m_PriceChgFromClose"))
        self.change_pct_from_close: float | None = _float(raw.get("m_PercentChgFromClose"))
        self.transaction_type: str | None = raw.get("TransactionType")

    def __repr__(self) -> str:
        return (
            f"TradeUpdate(command={self.command!r}, stock_id={self.stock_id}, "
            f"price={self.price}, volume={self.volume})"
        )


# ---------------------------------------------------------------------------
# ActiveOrders update model (COMMAND mode)
# ---------------------------------------------------------------------------


class OrderUpdate:
    """A live order status update from the ActiveOrders stream (COMMAND mode).

    Lightstreamer COMMAND mode delivers ADD/UPDATE/DELETE events for each
    order in the client's active order book.  Use ``command`` to determine
    the event type:
    - ``"ADD"``    — new order appeared (just submitted or snapshot)
    - ``"UPDATE"`` — order state changed (partial fill, status change)
    - ``"DELETE"`` — order removed from the active book (filled, cancelled)

    Attributes:
        command: ``"ADD"``, ``"UPDATE"``, or ``"DELETE"``.
        key: Lightstreamer row key (unique per order entry).
        stock_id: Internal stock identifier.
        order_number: Exchange order number (the order ID for REST calls).
        order_date: Date string when the order was placed.
        price: Order price in EGP (0 for market orders).
        order_type: Order type code.
        order_type_ui: Human-readable order type.
        quantity: Total order quantity (shares).
        executed_quantity: Filled quantity (shares).
        remaining_quantity: Unfilled quantity (shares).
        avg_price: Average executed price in EGP.
        status: Order status code.
        status_ui: Human-readable order status string.
        fix_status: FIX protocol status code.
        expire_date: Order expiry date string (GTD orders only).
        is_locked: True if the order is locked (being processed).
        market_id: Market identifier.
        profile_id: Client account profile identifier.
        raw: Full raw field dict.
    """

    __slots__ = (
        "avg_price",
        "command",
        "executed_quantity",
        "expire_date",
        "fix_status",
        "is_locked",
        "key",
        "market_id",
        "order_date",
        "order_number",
        "order_type",
        "order_type_ui",
        "price",
        "profile_id",
        "quantity",
        "raw",
        "remaining_quantity",
        "status",
        "status_ui",
        "stock_id",
    )

    def __init__(self, raw: dict[str, str | None]) -> None:
        self.raw = raw
        self.command: str | None = raw.get("command")
        self.key: str | None = raw.get("key")
        self.stock_id: int | None = _int(raw.get("m_SymbolID"))
        self.order_number: str | None = raw.get("m_OrderNumber") or raw.get("key")
        self.order_date: str | None = raw.get("m_OrderDate")
        self.price: float | None = _float(raw.get("m_OrderPrice"))
        self.order_type: str | None = raw.get("m_OrderType")
        self.order_type_ui: str | None = raw.get("m_OrderTypeUI")
        self.quantity: int | None = _int(raw.get("m_OrderQuantity"))
        self.executed_quantity: int | None = _int(raw.get("m_OrderExecQuantity"))
        self.remaining_quantity: int | None = _int(raw.get("m_OrderRemainingQuantity"))
        self.avg_price: float | None = _float(raw.get("m_OrderAvgPrice"))
        self.status: int | None = _int(raw.get("m_OrderStatus"))
        self.status_ui: str | None = raw.get("m_OrderStatusUI")
        self.fix_status: str | None = raw.get("m_OrderFixStatus")
        self.expire_date: str | None = raw.get("m_ExpireDate")
        self.is_locked: bool | None = _bool(raw.get("m_IsOrderLocked"))
        self.market_id: int | None = _int(raw.get("m_MarketID"))
        self.profile_id: int | None = _int(raw.get("m_ClientAccProfileID"))

    def __repr__(self) -> str:
        return (
            f"OrderUpdate(command={self.command!r}, order_number={self.order_number!r}, "
            f"status_ui={self.status_ui!r}, qty={self.quantity}, "
            f"executed={self.executed_quantity})"
        )


# ---------------------------------------------------------------------------
# Private helpers — safe type coercions
# ---------------------------------------------------------------------------


def _float(v: str | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        # Some integer fields come as floats (e.g. "12345.0")
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _bool(v: str | None) -> bool | None:
    if v is None:
        return None
    return v.lower() in ("true", "1", "yes")
