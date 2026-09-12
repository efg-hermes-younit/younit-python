"""Pydantic models for portfolio, positions, and buying power."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class PortfolioSummary(BaseModel):
    """Portfolio summary returned by GET /api/portfolio/GetPortfolioSummary.

    Attributes:
        client_id: Internal client identifier.
        market_id: Market identifier (1 = EGX).
        total_cash: Total cash balance in the account currency.
        total_stocks: Total value of stock holdings.
        total_balance: Total account balance (cash + stocks).
        realized_profit: Cumulative realized profit/loss.
        unrealized_profit: Unrealized profit/loss on open positions.
        profit_or_loss: Combined profit/loss figure.
        unrealized_profit_pct: Unrealized profit/loss as a percentage.
        currency: Currency short name (e.g. ``"EGP"``).
    """

    model_config = ConfigDict(populate_by_name=True)

    client_id: int | None = Field(default=None, alias="ClientId")
    market_id: int | None = Field(default=None, alias="marketId")
    total_cash: float = Field(default=0.0, alias="totalCash")
    total_stocks: float = Field(default=0.0, alias="totalStocks")
    total_balance: float = Field(default=0.0, alias="totalBalance")
    realized_profit: float = Field(default=0.0, alias="realizedProfit")
    unrealized_profit: float = Field(default=0.0, alias="unRealizedProfit")
    profit_or_loss: float = Field(default=0.0, alias="profitOrLoss")
    unrealized_profit_pct: float = Field(default=0.0, alias="unRealizedProfitPercentage")
    currency: str | None = Field(default=None, alias="currencyShortName")


class Position(BaseModel):
    """A single stock position returned by GET /api/portfolio/GetStocksPortfolio.

    Attributes:
        stock_id: Internal stock identifier (``securityID``).
        symbol: EGX ticker symbol, stripped of the exchange suffix (e.g.
            raw ``"FWRY.CA"`` -> ``"FWRY"``), matching the convention used
            for ``reuterCode`` elsewhere (see ``SymbolCache.load``,
            ``StockInfo``/``Quote`` parsing in endpoints/market_data.py).
        name: English short name of the stock.
        name_ar: Arabic short name of the stock.
        quantity: Number of shares held.
        unsettled_qty: Unsettled (T+N) share quantity.
        qty_valid_for_sale: Quantity currently available to sell.
        frozen_qty: Frozen/blocked quantity.
        average_price: Average cost basis per share.
        market_price: Current market price per share.
        market_value: Current market value of the position (``holdingValue``).
        total_value: Total position value.
        unrealized_pnl: Unrealized profit/loss.
        unrealized_pnl_pct: Unrealized profit/loss as a percentage.
        realized_pnl: Realized profit/loss.
        profit_or_loss: Combined profit/loss figure.
        currency: Currency short name (e.g. ``"EGP"``).
        is_fund: Whether this position is a mutual fund.
        is_suspended: Whether the stock is currently suspended.
    """

    model_config = ConfigDict(populate_by_name=True)

    stock_id: int | None = Field(default=None, alias="securityID")
    symbol: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ReuterID", "reuterID"),
        alias="ReuterID",
    )
    name: str | None = Field(default=None, alias="shortNameE")
    name_ar: str | None = Field(default=None, alias="shortNameA")
    quantity: int = Field(default=0, alias="quantity")
    unsettled_qty: int = Field(default=0, alias="unSettledQty")
    qty_valid_for_sale: int = Field(default=0, alias="quantiyValidForSale")
    frozen_qty: int = Field(default=0, alias="frozenQty")
    average_price: float = Field(default=0.0, alias="averageCost")
    market_price: float = Field(default=0.0, alias="marketPrice")
    market_value: float = Field(default=0.0, alias="holdingValue")
    total_value: float = Field(default=0.0, alias="totalValue")
    unrealized_pnl: float = Field(default=0.0, alias="unRealizedProfit")
    unrealized_pnl_pct: float = Field(default=0.0, alias="unRealizedProfitPercentage")
    realized_pnl: float = Field(default=0.0, alias="realizedProfit")
    profit_or_loss: float = Field(default=0.0, alias="profitOrLoss")
    currency: str | None = Field(default=None, alias="currencyShortName")
    is_fund: bool = Field(default=False, alias="isFund")
    is_suspended: bool = Field(default=False, alias="isSuspended")

    @field_validator("symbol", mode="before")
    @classmethod
    def _strip_exchange_suffix(cls, v: object) -> str | None:
        # Raw value is e.g. "FWRY.CA"; strip the exchange suffix, same
        # convention as SymbolCache.load and endpoints/market_data.py.
        if isinstance(v, str) and v:
            return v.split(".")[0] or None
        return v


class FundPosition(BaseModel):
    """A single fund position returned by GET /api/portfolio/GetPortfolioSecurities.

    Rows are filtered to ``isFund=True`` entries of that endpoint's combined
    ``securityPositions`` list (which holds both stock and fund rows) —
    GetStocksPortfolio/``Position`` never returns fund holdings, confirmed live.

    Attributes:
        fund_id: Internal fund identifier (``securityID``).
        symbol: Fund ticker, stripped of the exchange suffix, same convention
            as ``Position.symbol``.
        name: English short name of the fund.
        name_ar: Arabic short name of the fund.
        fund_type: Fund category/type (e.g. money market, equity).
        quantity: Number of units held.
        unsettled_qty: Unsettled (T+N) unit quantity.
        qty_valid_for_sale: Quantity currently available to redeem.
        frozen_qty: Frozen/blocked quantity.
        average_price: Average cost basis per unit.
        market_price: Current market price per unit.
        market_value: Current market value of the position (``holdingValue``).
        total_value: Total position value.
        unrealized_pnl: Unrealized profit/loss.
        unrealized_pnl_pct: Unrealized profit/loss as a percentage.
        realized_pnl: Realized profit/loss.
        profit_or_loss: Combined profit/loss figure.
        currency: Currency short name (e.g. ``"EGP"``).
        is_suspended: Whether the fund is currently suspended.
        is_invest: Whether additional investment (buying) is currently allowed.
        is_redeem: Whether redemption (selling) is currently allowed.
        show_unsettled_qty: Whether the UI should display unsettled quantity.
        show_frozen_qty: Whether the UI should display frozen quantity.
    """

    model_config = ConfigDict(populate_by_name=True)

    fund_id: int | None = Field(default=None, alias="securityID")
    symbol: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reuterID", "ReuterID"),
        alias="reuterID",
    )
    name: str | None = Field(default=None, alias="shortNameE")
    name_ar: str | None = Field(default=None, alias="shortNameA")
    fund_type: str | None = Field(default=None, alias="fundType")
    quantity: int = Field(default=0, alias="quantity")
    unsettled_qty: int = Field(default=0, alias="unSettledQty")
    qty_valid_for_sale: int = Field(default=0, alias="quantiyValidForSale")
    frozen_qty: int = Field(default=0, alias="frozenQty")
    average_price: float = Field(default=0.0, alias="averageCost")
    market_price: float = Field(default=0.0, alias="marketPrice")
    market_value: float = Field(default=0.0, alias="holdingValue")
    total_value: float = Field(default=0.0, alias="totalValue")
    unrealized_pnl: float = Field(default=0.0, alias="unRealizedProfit")
    unrealized_pnl_pct: float = Field(default=0.0, alias="unRealizedProfitPercentage")
    realized_pnl: float = Field(default=0.0, alias="realizedProfit")
    profit_or_loss: float = Field(default=0.0, alias="profitOrLoss")
    currency: str | None = Field(default=None, alias="currencyShortName")
    is_suspended: bool = Field(default=False, alias="isSuspended")
    is_invest: bool = Field(default=False, alias="isInvest")
    is_redeem: bool = Field(default=False, alias="isRedeem")
    show_unsettled_qty: bool = Field(default=False, alias="showUnsettledQty")
    show_frozen_qty: bool = Field(default=False, alias="showFrozenQty")

    @field_validator("symbol", mode="before")
    @classmethod
    def _strip_exchange_suffix(cls, v: object) -> str | None:
        # Raw value is e.g. "SIGP.CA"; same suffix-stripping convention as
        # Position.symbol.
        if isinstance(v, str) and v:
            return v.split(".")[0] or None
        return v


class BuyingPower(BaseModel):
    """Buying power and profile information for a specific stock.

    Returned by GET /api/v1/trading/buying-power/normal/{stockId}.

    The ``profile_id`` from this response is required when placing orders.

    Attributes:
        profile_id: The profile identifier required for order placement.
            This is the primary reason to call buying_power() before placing
            an order.
        profile_name: Human-readable label for the profile (e.g. ``"Cash"``).
        buying_power: Available buying power as a numeric value.
        buying_power_str: Available buying power as a formatted string.
        certificates_quantity_held: Number of certificates/shares currently held.
    """

    model_config = ConfigDict(populate_by_name=True)

    profile_id: int | None = Field(default=None, alias="profileID")
    profile_name: str | None = Field(default=None, alias="title")
    buying_power: float = Field(default=0.0, alias="rawValue")
    buying_power_str: str | None = Field(default=None, alias="value")
    certificates_quantity_held: int = Field(default=0, alias="certificatesQuantityHolded")
