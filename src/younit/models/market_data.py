"""Pydantic models for market data: quotes, stock info, movers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CAIRO_TZ = ZoneInfo("Africa/Cairo")


class Quote(BaseModel):
    """Current price snapshot for a stock.

    Returned by GET /api/stocks/stock-trading-info/{marketId}/{id}.

    Attributes:
        stock_id: Internal stock identifier.
        symbol: EGX ticker symbol.
        name: Company name.
        last: Last traded price in EGP.
        min_price: Minimum allowed order price in EGP (lower price limit).
        max_price: Maximum allowed order price in EGP (upper price limit).
        is_intraday: True if this stock supports intraday (T+0) trading.
        is_tplus1: True if this stock settles on T+1.
        market_id: Market identifier (1 = EGX).
    """

    model_config = ConfigDict(populate_by_name=True)

    stock_id: int | None = Field(default=None, alias="stockId")
    symbol: str | None = Field(default=None, alias="symbol")
    name: str | None = Field(default=None, alias="stockName")
    last: float = Field(default=0.0, alias="price")
    min_price: float = Field(default=0.0, alias="minPrice")
    max_price: float = Field(default=0.0, alias="maxPrice")
    is_intraday: bool = Field(default=False, alias="isIntraday")
    is_tplus1: bool = Field(default=False, alias="isTPlus1")
    market_id: int | None = Field(default=None, alias="marketId")


class StockInfo(BaseModel):
    """Detailed information about a stock, as returned by market listings.

    Used in list_stocks, trending_stocks, search_stocks.

    Attributes:
        stock_id: Internal stock identifier.
        symbol: EGX ticker symbol (e.g. ``"COMI"``).
        name: Company full name.
        market_id: Market identifier (1 = EGX).
        last: Last traded price in EGP.
        is_intraday: True if this stock supports intraday trading.
        is_tplus1: True if this stock settles T+1.
        security_class_id: Instrument-type classification (``_SecurityClassID``,
            see :data:`~younit.enums.SECURITY_CLASS_NAMES`). TEMPORARY: this
            is NOT live backend data — ``list_stocks()``'s own endpoint
            always returns this as null, so it's enriched client-side from
            a point-in-time snapshot (see
            ``younit._security_class_snapshot``). ``None`` if the stock
            isn't in that snapshot (e.g. listed after it was captured).
            Check :attr:`Client.security_class_snapshot_captured_at` for
            the snapshot's capture date. This scaffolding is meant to be
            removed once list_stocks()'s backend response includes
            ``_SecurityClassID`` natively — see
            ``younit._security_class_snapshot``'s module docstring for the
            removal checklist.
        security_class_name: Human-readable name for ``security_class_id``
            (e.g. ``"LocalSecurity_IN"``), looked up from
            :data:`~younit.enums.SECURITY_CLASS_NAMES`. Same temporary,
            snapshot-derived caveat as ``security_class_id`` applies.
        is_same_day_eligible: True if this stock is on the Intraday
            tradeable list (same-day/T0 eligible). Confirmed live: this
            list is exclusively class 1 (``LocalSecurity_IN``) securities —
            OTC stocks (``security_class_name == "OTC"``) and
            LocalSecurity_OUT (class 2) are never same-day eligible; not
            all class-1 stocks are on this list either, so this field
            reflects live list membership on every :meth:`Client.list_stocks`
            call, not something inferred from ``security_class_name`` alone.
    """

    model_config = ConfigDict(populate_by_name=True)

    stock_id: int | None = Field(default=None, alias="stockId")
    symbol: str | None = Field(default=None, alias="symbol")
    name: str | None = Field(default=None, alias="stockName")
    short_name: str | None = Field(default=None, alias="shortName")
    reuters_code: str | None = Field(default=None, alias="reuterCode")
    market_id: int | None = Field(default=None, alias="marketId")
    currency: str | None = Field(default=None, alias="currencyShortName")
    is_auction: bool = Field(default=False, alias="isAuctionStock")
    last: float = Field(default=0.0, alias="price")
    is_intraday: bool = Field(default=False, alias="isIntraday")
    is_tplus1: bool = Field(default=False, alias="isTPlus1")
    security_class_id: int | None = Field(default=None, alias="_SecurityClassID")
    security_class_name: str | None = Field(default=None)
    is_same_day_eligible: bool = Field(default=False)


class MarketMover(BaseModel):
    """A stock appearing in the top gainers or losers list.

    Returned by GET /api/stocks/top-gainers-losers/{marketId}.

    Attributes:
        stock_id: Internal stock identifier.
        symbol: EGX ticker symbol.
        name: Company name.
        last: Last traded price in EGP.
        change: Price change from previous close in EGP.
        change_pct: Price change percentage.
        volume: Trading volume.
        rank: Position in the gainers/losers ranking (1 = highest).
    """

    model_config = ConfigDict(populate_by_name=True)

    stock_id: int | None = Field(default=None, alias="stockId")
    symbol: str | None = Field(default=None, alias="symbol")
    name: str | None = Field(default=None, alias="stockName")
    last: float = Field(default=0.0, alias="price")
    change: float = Field(default=0.0, alias="change")
    change_pct: float = Field(default=0.0, alias="changePercent")
    volume: int = Field(default=0, alias="volume")
    rank: int | None = Field(default=None, alias="rank")


class HistoricalCandle(BaseModel):
    """A single OHLCV candle from the historical charting data feed.

    Returned by ``GET /api/charts/GetChartingHistoricalDataFeed``
    (field ``chartingDataViewModel`` inside the nested response).

    Attributes:
        timestamp: Candle date/time, as a timezone-aware datetime in
            Africa/Cairo local time. The raw value is a naive ISO 8601
            string (e.g. ``"2026-08-26T00:00:00"``) with no timezone
            marker; it is ASSUMED to already represent Cairo local time
            (see the ``_parse_timestamp`` validator below) — this is
            unconfirmed with the backend team.
        open: Opening price in EGP.
        high: Highest price in EGP.
        low: Lowest price in EGP.
        close: Closing price in EGP (field ``price`` in the raw response).
        volume: Number of shares traded in the period.
    """

    model_config = ConfigDict(populate_by_name=True)

    timestamp: datetime | None = Field(default=None, alias="dateTime")
    open: float = Field(default=0.0, alias="openPrice")
    high: float = Field(default=0.0, alias="highPrice")
    low: float = Field(default=0.0, alias="lowPrice")
    close: float = Field(default=0.0, alias="price")
    volume: float = Field(default=0.0, alias="volume")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp(cls, v: object) -> datetime | None:
        # ASSUMPTION (unconfirmed with backend team): the raw string has no
        # timezone marker (e.g. "2026-08-26T00:00:00"). We treat it as
        # already being Cairo local time and attach Africa/Cairo directly.
        # Alternative interpretation, not yet ruled out: the naive value is
        # actually UTC and should be converted to Cairo instead of just
        # tagged. Revisit once confirmed.
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=_CAIRO_TZ)
        if not isinstance(v, str):
            return None
        try:
            return datetime.fromisoformat(v).replace(tzinfo=_CAIRO_TZ)
        except ValueError:
            return None

    @field_validator("open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def _coerce_float(cls, v: object) -> float:
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def print_table(cls, candles: "list[HistoricalCandle]") -> None:
        """Print a list of candles as a formatted, aligned table.

        Convenience for examples/CLI use — not used internally by the SDK.

        Args:
            candles: List of HistoricalCandle to display.
        """
        headers = ("Date", "Open", "High", "Low", "Close", "Volume")
        widths = (20, 8, 8, 8, 8, 12)
        fmt = "  " + "  ".join(
            f"{{:<{w}}}" if i == 0 else f"{{:>{w}}}" for i, w in enumerate(widths)
        )
        print(fmt.format(*headers))
        print(fmt.format(*("-" * w for w in widths)))
        for c in candles:
            print(
                fmt.format(
                    c.timestamp.strftime("%Y-%m-%d") if c.timestamp else "",
                    f"{c.open:.2f}",
                    f"{c.high:.2f}",
                    f"{c.low:.2f}",
                    f"{c.close:.2f}",
                    f"{c.volume:,.0f}",
                )
            )
