"""Pydantic models for mutual fund data."""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CAIRO_TZ = ZoneInfo("Africa/Cairo")


def _parse_utc_to_cairo(v: object) -> datetime | None:
    """Parse a raw UTC ISO 8601 string (explicit ``Z`` marker) to Cairo local time."""
    if isinstance(v, datetime):
        dt = v if v.tzinfo else v.replace(tzinfo=UTC)
        return dt.astimezone(_CAIRO_TZ)
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt.astimezone(_CAIRO_TZ)
    except ValueError:
        return None


class Fund(BaseModel):
    """A mutual fund listed on the platform.

    Returned by GET /api/Funds/{marketId}.

    Attributes:
        fund_id: Internal fund identifier (``securityID``).
        name: Fund name.
        fund_type: Fund category (e.g. ``"Commodities"``).
        nav: Current price / NAV per unit.
        nav_change: Absolute price change since last session.
        nav_change_pct: Percentage price change since last session.
        currency: Currency short name (e.g. ``"EGP"``).
        minimum_subscription: Minimum subscription amount.
        subscription_fees: Subscription fee rate.
        redemption_fees: Redemption fee rate.
        total_overheads_pct: Total overhead charges as a percentage.
        cut_off_time: Daily order cut-off time, as a timezone-aware
            ``time`` in Africa/Cairo local time (raw value e.g.
            ``"09:00 AM"``, no date component so it is modelled as a
            ``time`` rather than a ``datetime``).
        launch_date: Fund launch date, as a timezone-aware datetime in
            Africa/Cairo local time (raw value is UTC, e.g.
            ``"2026-01-28T07:00:00Z"``).
        is_ipo: Whether the fund is in an active IPO period.
        can_invest: Whether subscriptions are currently allowed.
        is_gold_fund: Whether this is a gold-backed fund.
        is_user_subscribed: Whether the authenticated user holds units.
    """

    model_config = ConfigDict(populate_by_name=True)

    fund_id: int | None = Field(default=None, alias="securityID")
    name: str | None = Field(default=None, alias="securityName")
    fund_type: str | None = Field(default=None, alias="fundType")
    nav: float | None = Field(default=None, alias="price")
    nav_change: float | None = Field(default=None, alias="priceChange")
    nav_change_pct: float | None = Field(default=None, alias="priceChangePercentage")
    currency: str | None = Field(default=None, alias="currencyShortName")
    currency_code: int | None = Field(default=None, alias="currencyCode")
    minimum_subscription: float | None = Field(default=None, alias="minFundAmount")
    subscription_fees: float | None = Field(default=None, alias="subscriptionFees")
    redemption_fees: float | None = Field(default=None, alias="redemptionFees")
    total_overheads_pct: float | None = Field(default=None, alias="totalOverheadsPercentage")
    cut_off_time: time | None = Field(default=None, alias="cutOffTime")
    launch_date: datetime | None = Field(default=None, alias="launchDate")
    is_ipo: bool = Field(default=False, alias="isIPO")
    can_invest: bool = Field(default=False, alias="canInvest")
    is_gold_fund: bool = Field(default=False, alias="isGoldFund")
    is_user_subscribed: bool = Field(default=False, alias="isUserSubscribed")

    @field_validator("cut_off_time", mode="before")
    @classmethod
    def _parse_cut_off_time(cls, v: object) -> time | None:
        # Raw value observed live as e.g. "09:00 AM" — no date component and
        # no timezone marker. ASSUMED to already be Cairo local time (this
        # brokerage's cut-off is presumably always quoted in local time),
        # unconfirmed with the backend team.
        if isinstance(v, time):
            return v if v.tzinfo else v.replace(tzinfo=_CAIRO_TZ)
        if not isinstance(v, str):
            return None
        try:
            return datetime.strptime(v, "%I:%M %p").time().replace(tzinfo=_CAIRO_TZ)
        except ValueError:
            return None

    @field_validator("launch_date", mode="before")
    @classmethod
    def _parse_launch_date(cls, v: object) -> datetime | None:
        return _parse_utc_to_cairo(v)

    @classmethod
    def print_table(cls, funds: "list[Fund]") -> None:
        """Print a list of funds as a formatted, aligned table.

        Convenience for examples/CLI use — not used internally by the SDK.

        Args:
            funds: List of Fund to display.
        """
        headers = ("ID", "Name", "Type", "NAV", "Chg %", "Ccy", "Subscribed")
        widths = (10, 40, 16, 10, 8, 6, 10)
        fmt = "  " + "  ".join(
            f"{{:<{w}}}" if i in (0, 1, 2) else f"{{:>{w}}}" for i, w in enumerate(widths)
        )
        print(fmt.format(*headers))
        print(fmt.format(*("-" * w for w in widths)))
        for f in funds:
            print(
                fmt.format(
                    f.fund_id if f.fund_id is not None else "",
                    f.name or "",
                    f.fund_type or "",
                    f"{f.nav:.4f}" if f.nav is not None else "",
                    f"{f.nav_change_pct:+.2f}" if f.nav_change_pct is not None else "",
                    f.currency or "",
                    str(f.is_user_subscribed),
                )
            )


class PerformanceDataPoint(BaseModel):
    """A single point in a fund's performance chart.

    Attributes:
        date: Data point date, as a timezone-aware datetime in Africa/Cairo
            local time (raw value is UTC, e.g. ``"2026-01-27T22:00:00Z"``).
        value: NAV / price at this date.
        currency: Currency short name (e.g. ``"EGP"``).
    """

    model_config = ConfigDict(populate_by_name=True)

    date: datetime | None = Field(default=None, alias="date")
    value: float | None = Field(default=None, alias="price")
    currency: str | None = Field(default=None, alias="currencyShortName")

    @field_validator("date", mode="before")
    @classmethod
    def _parse_date(cls, v: object) -> datetime | None:
        return _parse_utc_to_cairo(v)


class FundPerformance(BaseModel):
    """Performance chart data for a mutual fund.

    Returned by GET /api/Funds/PerformanceChart/{marketId}/{Id}/{FundChartFilterType}.

    Attributes:
        fund_id: Internal fund identifier.
        chart_data: List of (date, NAV) data points.
        filter_type: The time filter applied (e.g. 1M, 3M, 1Y).
    """

    model_config = ConfigDict(populate_by_name=True)

    fund_id: int | None = Field(default=None, alias="fundId")
    chart_data: list[PerformanceDataPoint] = Field(default_factory=list, alias="chartData")
    filter_type: int | None = Field(default=None, alias="filterType")


class FundOrderHistoryEntry(BaseModel):
    """A single row from GET /api/Funds/order-history/{MarketId}/{ProfileId}.

    Maps to the ``FundsOrderHistoryResultDto`` schema in the OpenAPI spec.

    Attributes:
        order_date: When the order was placed, parsed from the raw
            ``MM/DD/YYYY HH:MM:SS`` string this endpoint actually sends
            (e.g. ``"09/07/2026 12:39:54"``) — NOT ISO 8601 like every
            other datetime field in this SDK. Confirmed via a live
            capture, not just the spec (which only declares it as an
            unformatted string). This format inconsistency is unexplained
            and worth confirming with the backend team.
    """

    model_config = ConfigDict(populate_by_name=True)

    order_id: int | None = Field(default=None, alias="orderID")
    fund_id: int | None = Field(default=None, alias="securityId")
    profile_id: int | None = Field(default=None, alias="clientAccProfileID")
    quantity: int | None = Field(default=None, alias="quantity")
    executed_quantity: int | None = Field(default=None, alias="executedQuantity")
    fees: float | None = Field(default=None, alias="fees")
    price: float | None = Field(default=None, alias="price")
    order_amount: float | None = Field(default=None, alias="orderAmount")
    order_type: str | None = Field(default=None, alias="orderType")
    order_date: datetime | None = Field(default=None, alias="orderDate")
    status: str | None = Field(default=None, alias="status")
    currency: str | None = Field(default=None, alias="currencyShortName")
    fund_type: str | None = Field(default=None, alias="fundType")
    fund_name: str | None = Field(default=None, alias="fundName")
    fees_display_name: str | None = Field(default=None, alias="feesDisplayName")
    status_color: str | None = Field(default=None, alias="statusColor")
    is_active: bool | None = Field(default=None, alias="isActive")
    is_redeem: bool | None = Field(default=None, alias="isRedeem")
    can_edit: bool | None = Field(default=None, alias="canEdit")
    can_cancel: bool | None = Field(default=None, alias="canCancel")

    @field_validator("order_date", mode="before")
    @classmethod
    def _parse_order_date(cls, v: object) -> datetime | None:
        # Raw value observed live as e.g. "09/07/2026 12:39:54" — MM/DD/YYYY
        # HH:MM:SS, unlike every other ISO 8601 datetime in this API.
        if isinstance(v, datetime):
            return v
        if not isinstance(v, str):
            return None
        try:
            return datetime.strptime(v, "%m/%d/%Y %H:%M:%S")
        except ValueError:
            return None
