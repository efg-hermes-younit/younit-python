# Data Models Reference

> **Note on descriptions:** No model in `src/younit/models/` currently uses
> Pydantic's `Field(description=...)` metadata (verified by grep — zero
> matches). The descriptions below are therefore pulled from each class's
> docstring `Attributes:` section instead, since that is the only
> field-level documentation that exists in the code today. Unlike
> `Field(description=...)`, docstring text is **not** enforced by Pydantic
> and can silently drift from the field list — if you need docs that are
> guaranteed not to drift, migrate these docstrings to
> `Field(..., description="...")` first. Fields with no corresponding
> docstring entry are marked **needs a description** rather than guessed.

## Quote

Current price snapshot for a stock. Returned by `client.quote()` and `client.stock_info()` (alias).

Defined in [market_data.py](../src/younit/models/market_data.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `stock_id` | `int \| None` | `stockId` | Internal stock identifier. |
| `symbol` | `str \| None` | `symbol` | EGX ticker symbol. |
| `name` | `str \| None` | `stockName` | Company name. |
| `last` | `float` | `price` | Last traded price in EGP. |
| `min_price` | `float` | `minPrice` | Minimum allowed order price in EGP (lower price limit). |
| `max_price` | `float` | `maxPrice` | Maximum allowed order price in EGP (upper price limit). |
| `is_intraday` | `bool` | `isIntraday` | True if this stock supports intraday (T+0) trading. |
| `is_tplus1` | `bool` | `isTPlus1` | True if this stock settles on T+1. |
| `market_id` | `int \| None` | `marketId` | Market identifier (1 = EGX). |

## StockInfo

Detailed stock metadata as returned by market listings. Returned by `client.list_stocks()`, `client.top_gainers()`, `client.top_losers()`, `client.trending_stocks()`, and `client.search_stocks()` (the latter only populates `stock_id`/`symbol`, all other fields default).

Defined in [market_data.py](../src/younit/models/market_data.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `stock_id` | `int \| None` | `stockId` | Internal stock identifier. |
| `symbol` | `str \| None` | `symbol` | EGX ticker symbol (e.g. `"COMI"`). |
| `name` | `str \| None` | `stockName` | Company full name. |
| `short_name` | `str \| None` | `shortName` | *needs a description* |
| `reuters_code` | `str \| None` | `reuterCode` | *needs a description* |
| `market_id` | `int \| None` | `marketId` | Market identifier (1 = EGX). |
| `currency` | `str \| None` | `currencyShortName` | *needs a description* |
| `is_auction` | `bool` | `isAuctionStock` | *needs a description* |
| `last` | `float` | `price` | Last traded price in EGP. |
| `is_intraday` | `bool` | `isIntraday` | True if this stock supports intraday trading. |
| `is_tplus1` | `bool` | `isTPlus1` | True if this stock settles T+1. |
| `security_class_id` | `int \| None` | `_SecurityClassID` | Instrument-type classification. TEMPORARY: client-side-enriched from a point-in-time snapshot, not live data — see `younit._security_class_snapshot`. |
| `security_class_name` | `str \| None` | *(none)* | Human-readable name for `security_class_id` (e.g. `"LocalSecurity_IN"`, `"OTC"`, `"Tbills"`) — see `younit.enums.SECURITY_CLASS_NAMES`. |
| `is_same_day_eligible` | `bool` | *(none)* | True if this stock is on the live Intraday tradeable list (same-day/T0 eligible). |

`client.list_stocks()` also has three convenience wrappers for filtering on the two fields above without writing a manual list comprehension: `client.list_by_class(*class_names)` (OR-filter by `security_class_name`, raises `ValueError` on an unrecognized name), `client.list_same_day_eligible()`, and `client.list_otc()` (shorthand for `list_by_class("OTC")`).

## MarketMover

⚠️ **Dead model** — defined and exported from `younit.models` but not returned by any current `Client` method. `client.top_gainers()`/`client.top_losers()` actually return `list[StockInfo]` (confirmed in [market_data.py endpoint](../src/younit/endpoints/market_data.py)). [BUILD_SPEC.md](../BUILD_SPEC.md) still documents these methods as returning `list[MarketMover]` — that spec text is stale. See "Findings" below.

Defined in [market_data.py](../src/younit/models/market_data.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `stock_id` | `int \| None` | `stockId` | Internal stock identifier. |
| `symbol` | `str \| None` | `symbol` | EGX ticker symbol. |
| `name` | `str \| None` | `stockName` | Company name. |
| `last` | `float` | `price` | Last traded price in EGP. |
| `change` | `float` | `change` | Price change from previous close in EGP. |
| `change_pct` | `float` | `changePercent` | Price change percentage. |
| `volume` | `int` | `volume` | Trading volume. |
| `rank` | `int \| None` | `rank` | Position in the gainers/losers ranking (1 = highest). |

## HistoricalCandle

A single OHLCV candle. Returned by `client.historical_prices()`.

Defined in [market_data.py](../src/younit/models/market_data.py) as a Pydantic `BaseModel` (with a `field_validator` that coerces `open`/`high`/`low`/`close`/`volume` to `float`, defaulting to `0.0` on parse failure).

| Field | Type | Alias | Description |
|---|---|---|---|
| `timestamp` | `datetime \| None` | `dateTime` | Candle date/time, timezone-aware in Africa/Cairo local time. Raw value is a naive ISO 8601 string (e.g. `"2026-08-26T00:00:00"`); it is ASSUMED to already be Cairo local time (unconfirmed with backend team — see field_validator comment). |
| `open` | `float` | `openPrice` | Opening price in EGP. |
| `high` | `float` | `highPrice` | Highest price in EGP. |
| `low` | `float` | `lowPrice` | Lowest price in EGP. |
| `close` | `float` | `price` | Closing price in EGP (field `price` in the raw response). |
| `volume` | `float` | `volume` | Number of shares traded in the period. |

## AccountInfo

Client account information. Returned by `client.account_info()`.

Defined in [account.py](../src/younit/models/account.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `account_code` | `int \| None` | `accountCode` | Internal numeric account identifier. |
| `client_name` | `str \| None` | `clientName` | Client's full name (Arabic). |
| `name` | `str \| None` | `name` | Client's full name (same as client_name). |
| `email` | `str \| None` | `email` | Client's email address. |
| `mobile` | `str \| None` | `mobile` | Client's mobile phone number. |
| `investor_code` | `str \| None` | `investorCode` | Investor code assigned by the exchange. |
| `can_setup_datafeed` | `bool` | `canSetupDatafeed` | Whether the client can configure a live datafeed. |
| `is_live_datafeed` | `bool` | `isLiveDatafeed` | Whether the client has an active live datafeed. |
| `is_global_market_allowed` | `bool \| None` | `isGlobalMarketAllowed` | Whether global market trading is enabled. |
| `can_edit_mobile` | `bool` | `canEditMobile` | Whether the mobile number can be edited. |
| `can_edit_email` | `bool` | `canEditEmail` | Whether the email address can be edited. |

## Profile

⚠️ **Dead model** — defined and exported from `younit.models` but never instantiated anywhere in `src/` (no `Profile(` call site found). `profile_id`/`profile_name` values are surfaced instead as plain fields on [`BuyingPower`](#buyingpower). Not currently returned by any SDK method.

Defined in [account.py](../src/younit/models/account.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `profile_id` | `int` | `profileId` | Numeric identifier for this trading profile. Used in order placement and buying-power requests. |
| `profile_name` | `str \| None` | `profileName` | Human-readable name for this profile. |

## PortfolioSummary

Portfolio summary (cash, stocks, P&L). Returned by `client.portfolio()`.

Defined in [portfolio.py](../src/younit/models/portfolio.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `client_id` | `int \| None` | `ClientId` | Internal client identifier. |
| `market_id` | `int \| None` | `marketId` | Market identifier (1 = EGX). |
| `total_cash` | `float` | `totalCash` | Total cash balance in the account currency. |
| `total_stocks` | `float` | `totalStocks` | Total value of stock holdings. |
| `total_balance` | `float` | `totalBalance` | Total account balance (cash + stocks). |
| `realized_profit` | `float` | `realizedProfit` | Cumulative realized profit/loss. |
| `unrealized_profit` | `float` | `unRealizedProfit` | Unrealized profit/loss on open positions. |
| `profit_or_loss` | `float` | `profitOrLoss` | Combined profit/loss figure. |
| `unrealized_profit_pct` | `float` | `unRealizedProfitPercentage` | Unrealized profit/loss as a percentage. |
| `currency` | `str \| None` | `currencyShortName` | Currency short name (e.g. `"EGP"`). |

## Position

A single stock position. Returned by `client.positions()` and `client.position()`.

Defined in [portfolio.py](../src/younit/models/portfolio.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `stock_id` | `int \| None` | `securityID` | Internal stock identifier (`securityID`). |
| `symbol` | `str \| None` | `reuterID` | Reuters ticker ID for this stock. |
| `name` | `str \| None` | `shortNameE` | English short name of the stock. |
| `name_ar` | `str \| None` | `shortNameA` | Arabic short name of the stock. |
| `quantity` | `int` | `quantity` | Number of shares held. |
| `unsettled_qty` | `int` | `unSettledQty` | Unsettled (T+N) share quantity. |
| `qty_valid_for_sale` | `int` | `quantiyValidForSale` | Quantity currently available to sell. |
| `frozen_qty` | `int` | `frozenQty` | Frozen/blocked quantity. |
| `average_price` | `float` | `averageCost` | Average cost basis per share. |
| `market_price` | `float` | `marketPrice` | Current market price per share. |
| `market_value` | `float` | `holdingValue` | Current market value of the position (`holdingValue`). |
| `total_value` | `float` | `totalValue` | Total position value. |
| `unrealized_pnl` | `float` | `unRealizedProfit` | Unrealized profit/loss. |
| `unrealized_pnl_pct` | `float` | `unRealizedProfitPercentage` | Unrealized profit/loss as a percentage. |
| `realized_pnl` | `float` | `realizedProfit` | Realized profit/loss. |
| `profit_or_loss` | `float` | `profitOrLoss` | Combined profit/loss figure. |
| `currency` | `str \| None` | `currencyShortName` | Currency short name (e.g. `"EGP"`). |
| `is_fund` | `bool` | `isFund` | Whether this position is a mutual fund. |
| `is_suspended` | `bool` | `isSuspended` | Whether the stock is currently suspended. |

> Note: the alias `quantiyValidForSale` (missing an `t`) is a typo in the upstream API's raw JSON field name, faithfully mirrored here — not a bug in this SDK.

## FundPosition

A single fund position. Returned by `client.fund_positions()` and `client.fund_position()`.

Defined in [portfolio.py](../src/younit/models/portfolio.py) as a Pydantic `BaseModel`. Rows come from `GET /api/portfolio/GetPortfolioSecurities`, filtered to `isFund=True` entries of that endpoint's combined `securityPositions` list (which holds both stock and fund rows) — `GetStocksPortfolio`/`Position` never returns fund holdings, confirmed live.

| Field | Type | Alias | Description |
|---|---|---|---|
| `fund_id` | `int \| None` | `securityID` | Internal fund identifier (`securityID`). |
| `symbol` | `str \| None` | `reuterID` (`reuterID`, `ReuterID`) | Fund ticker, stripped of the exchange suffix, same convention as `Position.symbol`. |
| `name` | `str \| None` | `shortNameE` | English short name of the fund. |
| `name_ar` | `str \| None` | `shortNameA` | Arabic short name of the fund. |
| `fund_type` | `str \| None` | `fundType` | Fund category/type (e.g. money market, equity). |
| `quantity` | `int` | `quantity` | Number of units held. |
| `unsettled_qty` | `int` | `unSettledQty` | Unsettled (T+N) unit quantity. |
| `qty_valid_for_sale` | `int` | `quantiyValidForSale` | Quantity currently available to redeem. |
| `frozen_qty` | `int` | `frozenQty` | Frozen/blocked quantity. |
| `average_price` | `float` | `averageCost` | Average cost basis per unit. |
| `market_price` | `float` | `marketPrice` | Current market price per unit. |
| `market_value` | `float` | `holdingValue` | Current market value of the position (`holdingValue`). |
| `total_value` | `float` | `totalValue` | Total position value. |
| `unrealized_pnl` | `float` | `unRealizedProfit` | Unrealized profit/loss. |
| `unrealized_pnl_pct` | `float` | `unRealizedProfitPercentage` | Unrealized profit/loss as a percentage. |
| `realized_pnl` | `float` | `realizedProfit` | Realized profit/loss. |
| `profit_or_loss` | `float` | `profitOrLoss` | Combined profit/loss figure. |
| `currency` | `str \| None` | `currencyShortName` | Currency short name (e.g. `"EGP"`). |
| `is_suspended` | `bool` | `isSuspended` | Whether the fund is currently suspended. |
| `is_invest` | `bool` | `isInvest` | Whether additional investment (buying) is currently allowed. |
| `is_redeem` | `bool` | `isRedeem` | Whether redemption (selling) is currently allowed. |
| `show_unsettled_qty` | `bool` | `showUnsettledQty` | Whether the UI should display unsettled quantity. |
| `show_frozen_qty` | `bool` | `showFrozenQty` | Whether the UI should display frozen quantity. |

> Note: unlike `Position`, `FundPosition` has no `is_fund` field — rows are already pre-filtered to funds only before parsing.

## BuyingPower

Buying power and profile information for a stock; `profile_id` is required for order placement. Returned by `client.buying_power()`, and used internally by `client.buy()`/`client.sell()`/`client.place_order()`.

Defined in [portfolio.py](../src/younit/models/portfolio.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `profile_id` | `int \| None` | `profileID` | The profile identifier required for order placement. This is the primary reason to call `buying_power()` before placing an order. |
| `profile_name` | `str \| None` | `title` | Human-readable label for the profile (e.g. `"Cash"`). |
| `buying_power` | `float` | `rawValue` | Available buying power as a numeric value. |
| `buying_power_str` | `str \| None` | `value` | Available buying power as a formatted string. |
| `certificates_quantity_held` | `int` | `certificatesQuantityHolded` | Number of certificates/shares currently held. |

## Order

An order as returned by `GET /api/v1/orders/{orderId}/info`. Returned by `client.buy()`, `client.sell()`, `client.place_order()`, and `client.get_order()`.

Defined in [orders.py](../src/younit/models/orders.py) as a Pydantic `BaseModel` with `extra="allow"` (unrecognized API fields are kept, not dropped). Several fields accept multiple raw key spellings via `AliasChoices` because the live API and the OpenAPI spec disagree on casing.

| Field | Type | Alias (validation aliases in parentheses) | Description |
|---|---|---|---|
| `order_id` | `int \| None` | `OrderID` (`orderID`, `OrderID`, `orderId`) | The numeric order identifier. |
| `stock_id` | `int \| None` | `StockID` (`securityID`, `StockID`, `stockId`) | Internal stock identifier. None for fund order results. |
| `fund_id` | `int \| None` | `FundID` (`fundId`, `FundID`) | Internal fund identifier. None for stock order results. |
| `market_id` | `int \| None` | `MarketID` | Market identifier (1 = EGX). |
| `profile_id` | `int \| None` | `ProfileID` | The trading profile this order belongs to. |
| `client_id` | `int \| None` | `ClientID` (`clientID`, `ClientID`) | The account/client identifier that owns the order. |
| `operation_type` | `str \| None` | `OperationType` | Buy or sell. |
| `price` | `float \| None` | `Price` (`price`, `Price`) | Order price in EGP (None for market orders). |
| `quantity` | `int \| None` | `Quantity` (`quantity`, `Quantity`) | Number of shares ordered. |
| `filled_quantity` | `int \| None` | `FilledQuantity` | Number of shares filled so far. |
| `status` | `int \| None` | `Status` | Order status code, if returned. |
| `is_market_price` | `bool \| None` | `IsMarketPrice` | True if this is a market order. |
| `expire_date` | `datetime \| None` | `ExpiryDate` (`expireDate`, `ExpiryDate`) | Expiry date for Good Till Date orders. |
| `symbol` | `str \| None` | `Symbol` | *needs a description* |

> Per the class docstring, the live endpoint response has **no order status field** at the top level distinct from the request's own `ResultStatus` wrapper — `status` above may not reflect real order lifecycle state. Use the `ActiveOrders` stream (`OrderUpdate`) for live status instead.

## OrderRequest *(request body, not a response model)*

Maps to the `CreateNormalOrderRequest` OpenAPI schema for `POST /api/v1/orders/normal`. Built internally by `client.place_order()`/`client.buy()`/`client.sell()`; not returned to callers.

Defined in [orders.py](../src/younit/models/orders.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `profile_id` | `int` | `profileID` | *needs a description* |
| `stock_id` | `int` | `stockID` | *needs a description* |
| `order_category` | `OrderCategory` | `orderCategory` | *needs a description* |
| `operation_type` | `OperationType` | `operationType` | *needs a description* |
| `quantity` | `int` (`gt=0`) | `quantity` | *needs a description* |
| `price` | `float \| None` | `price` | *needs a description* |
| `order_expire_terms_id` | `OrderExpireTerm` | `orderExpireTermsID` | *needs a description* |
| `expire_date` | `datetime \| None` | `expireDate` | *needs a description* |
| `order_via` | `OrderVia` | `orderVia` | *needs a description* |
| `is_market_price` | `bool` | `isMarketPrice` | *needs a description* |
| `execution_instruction_id` | `ExecutionInstruction` | `executionInstructionId` | *needs a description* |
| `is_edit` | `bool` | `isEdit` | *needs a description* |
| `is_ipo` | `bool \| None` | `isIPO` | *needs a description* |
| `ipo_info_id` | `int \| None` | `ipoInfoID` | *needs a description* |

*(No `Attributes:` docstring section exists for this class — all fields need descriptions.)*

## Fund

A mutual fund listing. Returned by `client.list_funds()` and `client.fund()`.

Defined in [funds.py](../src/younit/models/funds.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `fund_id` | `int \| None` | `securityID` | Internal fund identifier (`securityID`). |
| `name` | `str \| None` | `securityName` | Fund name. |
| `fund_type` | `str \| None` | `fundType` | Fund category (e.g. `"Commodities"`). |
| `nav` | `float \| None` | `price` | Current price / NAV per unit. |
| `nav_change` | `float \| None` | `priceChange` | Absolute price change since last session. |
| `nav_change_pct` | `float \| None` | `priceChangePercentage` | Percentage price change since last session. |
| `currency` | `str \| None` | `currencyShortName` | Currency short name (e.g. `"EGP"`). |
| `currency_code` | `int \| None` | `currencyCode` | *needs a description* |
| `minimum_subscription` | `float \| None` | `minFundAmount` | Minimum subscription amount. |
| `subscription_fees` | `float \| None` | `subscriptionFees` | Subscription fee rate. |
| `redemption_fees` | `float \| None` | `redemptionFees` | Redemption fee rate. |
| `total_overheads_pct` | `float \| None` | `totalOverheadsPercentage` | Total overhead charges as a percentage. |
| `cut_off_time` | `time \| None` | `cutOffTime` | Daily order cut-off time, timezone-aware in Africa/Cairo local time. Raw value e.g. `"09:00 AM"` (no date component, modelled as `time` rather than `datetime`). |
| `launch_date` | `datetime \| None` | `launchDate` | Fund launch date, timezone-aware in Africa/Cairo local time. Raw value is UTC, e.g. `"2026-01-28T07:00:00Z"`. |
| `is_ipo` | `bool` | `isIPO` | Whether the fund is in an active IPO period. |
| `can_invest` | `bool` | `canInvest` | Whether subscriptions are currently allowed. |
| `is_gold_fund` | `bool` | `isGoldFund` | Whether this is a gold-backed fund. |
| `is_user_subscribed` | `bool` | `isUserSubscribed` | Whether the authenticated user holds units. |

## FundPerformance

Performance chart data for a fund. Returned by `client.fund_performance()`.

Defined in [funds.py](../src/younit/models/funds.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `fund_id` | `int \| None` | `fundId` | Internal fund identifier. |
| `chart_data` | `list[PerformanceDataPoint]` | `chartData` | List of (date, NAV) data points. |
| `filter_type` | `int \| None` | `filterType` | The time filter applied (e.g. 1M, 3M, 1Y). |

### PerformanceDataPoint

A single point in a fund's performance chart (nested in `FundPerformance.chart_data`).

Defined in [funds.py](../src/younit/models/funds.py) as a Pydantic `BaseModel`.

| Field | Type | Alias | Description |
|---|---|---|---|
| `date` | `datetime \| None` | `date` | Data point date, timezone-aware in Africa/Cairo local time. Raw value is UTC, e.g. `"2026-01-27T22:00:00Z"`. |
| `value` | `float \| None` | `price` | NAV / price at this date. |
| `currency` | `str \| None` | `currencyShortName` | Currency short name (e.g. `"EGP"`). |

## Streaming update models

These are plain Python classes (**not** Pydantic models, **not** dataclasses — ordinary classes using `__slots__`), constructed internally from raw Lightstreamer field dicts. All fields are read via `on_update` callbacks passed to `client.streaming.subscribe_*()`.

### Subscription

A `@dataclass` (the one dataclass in this module) representing an active Lightstreamer subscription. Returned by every `subscribe_*` method; pass to `client.streaming.unsubscribe()` to cancel.

Defined in [streaming.py](../src/younit/models/streaming.py).

| Field | Type | Description |
|---|---|---|
| `stream_type` | `str` | Human-readable stream name (e.g. `"SymbolStatistics"`). |
| `item` | `str` | Lightstreamer item name (e.g. `"sy12345"`). |
| `on_update` | `Callable[..., None]` | The user callback registered for this subscription. |
| `on_error` | `Callable[[Exception], None] \| None` | *(default `None`)* |
| `_ls_subscription` | `Any` | *(default `None`, `repr=False`)* Internal Lightstreamer subscription object. Do not use directly unless you need raw Lightstreamer control. |

### SymbolUpdate

Live price update for a single stock (SymbolStatistics stream). Delivered to callbacks passed to `client.streaming.subscribe_quote()`.

Plain class with `__slots__`, defined in [streaming.py](../src/younit/models/streaming.py). Any field not included in a given update is `None` (Lightstreamer only sends changed fields after the initial snapshot).

| Field | Type | Description |
|---|---|---|
| `stock_id` | `int \| None` | Internal stock identifier. |
| `symbol` | `str \| None` | EGX ticker symbol. |
| `name` | `str \| None` | Company name. |
| `last` | `float \| None` | Last traded price in EGP. |
| `open` | `float \| None` | Opening price in EGP. |
| `close` | `float \| None` | Previous close price in EGP. |
| `high` | `float \| None` | Intraday high in EGP. |
| `low` | `float \| None` | Intraday low in EGP. |
| `bid` | `float \| None` | Best bid price in EGP. |
| `bid_volume` | `int \| None` | Best bid volume (shares). |
| `ask` | `float \| None` | Best ask price in EGP. |
| `ask_volume` | `int \| None` | Best ask volume (shares). |
| `volume` | `int \| None` | Total traded volume (shares). |
| `value` | `float \| None` | Total traded value in EGP. |
| `trades_count` | `int \| None` | Number of executed trades today. |
| `change` | `float \| None` | Price change from previous close in EGP. |
| `change_pct` | `float \| None` | Price change as a percentage. |
| `reference_price` | `float \| None` | Reference (base) price in EGP. |
| `week52_high` | `float \| None` | 52-week high price in EGP. |
| `week52_low` | `float \| None` | 52-week low price in EGP. |
| `market_cap` | `float \| None` | Market capitalisation in EGP. |
| `status_id` | `int \| None` | Numeric symbol status code. |
| `status` | `str \| None` | Human-readable symbol status. |
| `last_updated` | `str \| None` | Timestamp string of last update. |
| `raw` | `dict[str, str \| None]` | Full raw field dict from Lightstreamer for advanced use. |

### IndexUpdate

Live value update for a market index (IndexStatistics stream). Delivered to callbacks passed to `client.streaming.subscribe_index()`.

Plain class with `__slots__`, defined in [streaming.py](../src/younit/models/streaming.py).

| Field | Type | Description |
|---|---|---|
| `index_id` | `int \| None` | Internal index identifier. |
| `name` | `str \| None` | Index name in English. |
| `value` | `float \| None` | Current index value. |
| `open` | `float \| None` | Opening index value. |
| `close` | `float \| None` | Previous close value. |
| `high` | `float \| None` | Intraday high. |
| `low` | `float \| None` | Intraday low. |
| `week52_high` | `float \| None` | 52-week high. |
| `week52_low` | `float \| None` | 52-week low. |
| `net_change` | `float \| None` | Net change from previous close. |
| `change_pct` | `float \| None` | Percentage change (note: raw field is `m_PrecentChange`, a typo in the upstream API, not this SDK). |
| `traded_value` | `float \| None` | Total traded value in EGP. |
| `traded_volume` | `float \| None` | Total traded volume. |
| `raw` | `dict[str, str \| None]` | Full raw field dict. |

### MarketUpdate

Aggregated market statistics (MarketStatistics stream). Delivered to callbacks passed to `client.streaming.subscribe_market()`.

Plain class with `__slots__`, defined in [streaming.py](../src/younit/models/streaming.py).

| Field | Type | Description |
|---|---|---|
| `market_id` | `int \| None` | Internal market identifier (1 = EGX). |
| `name` | `str \| None` | Market name in English. |
| `status` | `str \| None` | Market status string (e.g. `"Open"`, `"Closed"`). |
| `traded_value` | `float \| None` | Total market traded value in EGP. |
| `traded_volume` | `float \| None` | Total market traded volume (shares). |
| `trades_count` | `int \| None` | Total number of trades executed today. |
| `symbols_traded` | `int \| None` | Number of symbols with at least one trade today. |
| `advances` | `int \| None` | Number of advancing (gaining) symbols. |
| `declines` | `int \| None` | Number of declining symbols. |
| `unchanged` | `int \| None` | Number of unchanged symbols. |
| `market_time` | `str \| None` | Current market time string. |
| `open_time` | `str \| None` | Market open time string. |
| `close_time` | `str \| None` | Market close time string. |
| `raw` | `dict[str, str \| None]` | Full raw field dict. |

### TradeUpdate

A single executed trade tape entry (SecurityTrades stream, COMMAND mode). Delivered to callbacks passed to `client.streaming.subscribe_trades()`.

Plain class with `__slots__`, defined in [streaming.py](../src/younit/models/streaming.py).

| Field | Type | Description |
|---|---|---|
| `command` | `str \| None` | Lightstreamer command: `"ADD"`, `"UPDATE"`, or `"DELETE"`. |
| `key` | `str \| None` | Lightstreamer row key (unique per trade entry). |
| `stock_id` | `int \| None` | Internal stock identifier. |
| `ticket_number` | `str \| None` | Exchange trade ticket number. |
| `price` | `float \| None` | Executed trade price in EGP. |
| `volume` | `int \| None` | Number of shares in this trade. |
| `last_updated` | `str \| None` | Timestamp string. |
| `change_from_close` | `float \| None` | Price change vs previous close in EGP. |
| `change_pct_from_close` | `float \| None` | Percentage change vs previous close. |
| `transaction_type` | `str \| None` | Buy/sell side indicator. |
| `raw` | `dict[str, str \| None]` | Full raw field dict. |

### OrderUpdate

Live order status update (ActiveOrders stream, COMMAND mode). Delivered to callbacks passed to `client.streaming.subscribe_orders()`; used by `client.place_order()`/`client.buy()`/`client.sell()` internally when `confirm=True`.

Plain class with `__slots__`, defined in [streaming.py](../src/younit/models/streaming.py).

| Field | Type | Description |
|---|---|---|
| `command` | `str \| None` | `"ADD"`, `"UPDATE"`, or `"DELETE"`. |
| `key` | `str \| None` | Lightstreamer row key (unique per order entry). |
| `stock_id` | `int \| None` | Internal stock identifier. |
| `order_number` | `str \| None` | Exchange order number (the order ID for REST calls). |
| `order_date` | `str \| None` | Date string when the order was placed. |
| `price` | `float \| None` | Order price in EGP (0 for market orders). |
| `order_type` | `str \| None` | Order type code. |
| `order_type_ui` | `str \| None` | Human-readable order type. |
| `quantity` | `int \| None` | Total order quantity (shares). |
| `executed_quantity` | `int \| None` | Filled quantity (shares). |
| `remaining_quantity` | `int \| None` | Unfilled quantity (shares). |
| `avg_price` | `float \| None` | Average executed price in EGP. |
| `status` | `str \| None`⚠ | Order status code (raw string, not coerced to `int` — see finding #6). |
| `status_ui` | `str \| None` | Human-readable order status string. |
| `fix_status` | `str \| None` | FIX protocol status code. |
| `expire_date` | `str \| None` | Order expiry date string (GTD orders only). |
| `is_locked` | `bool \| None` | True if the order is locked (being processed). |
| `market_id` | `int \| None` | Market identifier. |
| `profile_id` | `str \| None`⚠ | Client account profile identifier (raw string, not coerced to `int` — see finding #6). |
| `raw` | `dict[str, str \| None]` | Full raw field dict. |

## Findings (bugs / inconsistencies — not docs issues)

1. **`examples/09_amend_order.py` calls `.status` on a `bool`.** `Client.amend_order()` is typed to return `bool` (see [client.py](../src/younit/client.py)), but the example does `order = client.amend_order(...)` and then prints `order.status` — `bool` has no `.status` attribute, so this example would raise `AttributeError` at runtime if the `try` block is reached. This is an example bug, not a model bug.
2. **`MarketMover` model is dead code.** It's defined in [market_data.py](../src/younit/models/market_data.py) and exported from `younit.models`, but no endpoint or `Client` method returns it — `client.top_gainers()`/`client.top_losers()` return `list[StockInfo]` instead (confirmed in [endpoints/market_data.py](../src/younit/endpoints/market_data.py)). [BUILD_SPEC.md](../BUILD_SPEC.md) (line ~339-340) still documents these methods as returning `list[MarketMover]`, so the spec is stale relative to the implementation.
3. **`Profile` model is dead code.** Defined in [account.py](../src/younit/models/account.py) and exported, but never instantiated anywhere in `src/`. `profile_id`/`profile_name` are instead plain fields on `BuyingPower`.
4. **No field mismatches found between `examples/` and the actual response models.** Every `quote.*`, `info.*`, `bp.*`, `summary.*`, `pos.*`, `f.*`, `perf.*`, `order.*` (aside from finding #1), `latest.*`/`update.*` (streaming) attribute access in `examples/` was checked against the real class definitions — all exist with matching names.
5. **No `Field(description=...)` usage anywhere in `src/younit/models/`.** All field descriptions in this document were sourced from class-level `Attributes:` docstrings instead (see the note at the top of this file). Fields with no docstring entry are marked "needs a description" in the tables above rather than guessed.
6. **`OrderUpdate.status` and `OrderUpdate.profile_id` are typed `str | None` at runtime, not `int`.** Both are assigned directly from `raw.get(...)` with no `_int()` coercion, unlike sibling fields on the same class (`stock_id`, `market_id`, `quantity`, etc., which do use `_int()`). This is inconsistent with `Order.status` (`int | None`) and `BuyingPower.profile_id` (`int | None`) elsewhere in the SDK — code that does `int(update.status)` or compares `update.profile_id == some_int` should be aware these are strings. Not necessarily a bug (may reflect real API string values), but a type inconsistency worth confirming against a live payload.
