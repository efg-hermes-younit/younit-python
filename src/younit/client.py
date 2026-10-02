"""Younit Trading API — Python SDK Client.

The :class:`Client` is the single entry point for all SDK operations.
Construct one Client per end user (per ``tradingUuid``).

Example::

    from younit import Client

    client = Client(
        partner_id="your-partner-id",
        partner_secret="your-partner-secret",
        trading_uuid="client-trading-uuid",
        simulation=True,   # Always start in simulation mode
    )

    quote = client.quote("COMI")
    print(f"COMI last price: {quote.last} EGP")

Or use environment variables (recommended for production)::

    # Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
    client = Client()
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from younit import _security_class_snapshot
from younit.auth import IdentityProvider, TokenStore
from younit.config import _BASE_URL, Settings
from younit.endpoints import account as _account
from younit.endpoints import funds as _funds
from younit.endpoints import market_data as _market_data
from younit.endpoints import orders as _orders
from younit.endpoints import trading as _trading
from younit.enums import (
    SECURITY_CLASS_NAMES,
    ChartPeriod,
    ExecutionTerm,
    OperationType,
    OrderExpireTerm,
    OrderVia,
    SubOrderVia,
)
from younit.exceptions import OrderRejected
from younit.http import build_default_headers, build_httpx_client, raise_for_status
from younit.logging import configure_logging, get_logger
from younit.models.account import AccountInfo
from younit.models.funds import Fund, FundOrderHistoryEntry, FundPerformance
from younit.models.market_data import HistoricalCandle, Quote, StockInfo
from younit.models.orders import FundOrderRequest, Order, OrderHistoryEntry, OrderRequest
from younit.models.portfolio import BuyingPower, FundPosition, PortfolioSummary, Position
from younit.models.streaming import MarketUpdate, Subscription, SymbolUpdate, TopMover
from younit.streaming.client import StreamingClient
from younit.symbols import SymbolCache

_log = get_logger(__name__)

# Same Africa/Cairo convention used for datetime parsing elsewhere in the SDK
# (see models/funds.py, models/market_data.py).
_CAIRO_TZ = ZoneInfo("Africa/Cairo")

# sell()'s friendly `settlement` string -> OperationType, mirroring the
# `expire` string convention. "t0" and "same_day" are aliases for the same
# confirmed enum value (SELL_SAME_DAY).
_SETTLEMENT_TO_OPERATION_TYPE = {
    "t2": OperationType.SELL,
    "t0": OperationType.SELL_SAME_DAY,
    "same_day": OperationType.SELL_SAME_DAY,
    "t1": OperationType.SELL_T1,
}

# get_top_movers()'s real-equity filter over list_stocks()'s security_class_name
# — excludes Tbills, bonds, futures, etc., which have no meaningful
# change_pct/gainer-loser concept. Confirmed live: OTC == the OTC list-type
# category exactly (42/42, zero discrepancy).
_TOP_MOVERS_ELIGIBLE_CLASSES = frozenset({"LocalSecurity_IN", "LocalSecurity_OUT", "OTC"})

# MarketStatistics stream's m_MarketStatus -> friendly status string.
# Empirically derived from live observation (2026-09-05): "2" seen during
# EGX trading hours (11:30 AM, market open), "3" seen after close (3:42 PM).
# NOT yet officially confirmed by the backend team — if they confirm a
# different or fuller mapping (e.g. additional states like pre-open
# auction), update this accordingly.
_MARKET_STATUS_MAP = {"2": "open", "3": "closed", "20": "trade at last"}


def _parse_next_working_day(message: str) -> datetime | None:
    """Extract the next working day datetime from an overnight-order rejection message."""
    import re
    match = re.search(r"next working day\s+([\d/]+\s+[\d:]+\s+[APM]+)", message, re.IGNORECASE)
    if not match:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(match.group(1), fmt)
        except ValueError:
            continue
    return None


class Client:
    """Synchronous client for the Younit Trading API.

    Constructs one HTTP client, one identity provider, and one symbol cache.
    On construction, authenticates immediately and loads the symbol cache.

    All methods are synchronous. There is no async variant in v0.1.

    Args:
        partner_id: Partner identifier. Overrides ``EFG_PARTNER_ID``.
        partner_secret: Partner secret. Overrides ``EFG_PARTNER_SECRET``.
        trading_uuid: Client trading UUID. Overrides ``EFG_TRADING_UUID``.
        simulation: If True, uses simulation mode. Overrides ``EFG_SIMULATION``.
        company_code: Company code header. Overrides ``EFG_COMPANY_CODE``.
        identity_url: Identity provider URL. Overrides ``EFG_IDENTITY_URL``.
        accept_language: Language header. Overrides ``EFG_ACCEPT_LANGUAGE``.
        scopes: OAuth scopes list. Overrides ``EFG_SCOPES``.
        timeout_seconds: Request timeout. Overrides ``EFG_TIMEOUT_SECONDS``.
        token_store: Custom token store implementation. Defaults to in-memory.
        lazy_auth: If True, defers authentication until first API call.
            Defaults to False (authenticates on construction).
        lazy_symbols: If True, defers symbol cache loading until first resolve.
            Defaults to False (loads on construction).

    Raises:
        ConfigError: If required credentials are missing.
        InvalidCredentials: If partner credentials are rejected.
        AuthError: On any other authentication failure.
    """

    def __init__(
        self,
        *,
        partner_id: str | None = None,
        partner_secret: str | None = None,
        trading_uuid: str | None = None,
        simulation: bool | None = None,
        company_code: str | None = None,
        identity_url: str | None = None,
        accept_language: str | None = None,
        scopes: list[str] | None = None,
        timeout_seconds: float | None = None,
        token_store: TokenStore | None = None,
        lazy_auth: bool = False,
        lazy_symbols: bool = False,
        _base_url_override: str | None = None,  # internal/staging use only; not read from env
    ) -> None:
        # Build settings from constructor args + env vars
        kwargs: dict[str, Any] = {}
        if partner_id is not None:
            kwargs["partner_id"] = partner_id
        if partner_secret is not None:
            kwargs["partner_secret"] = partner_secret
        if trading_uuid is not None:
            kwargs["trading_uuid"] = trading_uuid
        if simulation is not None:
            kwargs["simulation"] = simulation
        if company_code is not None:
            kwargs["company_code"] = company_code
        if identity_url is not None:
            kwargs["identity_url"] = identity_url
        if accept_language is not None:
            kwargs["accept_language"] = accept_language
        if scopes is not None:
            kwargs["scopes"] = scopes
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds

        self._settings = Settings(**kwargs)
        self._base_url = _base_url_override if _base_url_override is not None else _BASE_URL

        configure_logging(
            level=self._settings.log_level,
            debug=self._settings.debug,
        )

        self._http = build_httpx_client(self._settings)
        self._default_headers = build_default_headers(self._settings)
        self._auth = IdentityProvider(self._settings, self._http, store=token_store)
        self._symbols = SymbolCache(self._settings.default_market_id)
        self._cached_profile_id: int | None = None
        self.streaming: StreamingClient = StreamingClient(
            settings=self._settings,
            token_getter=self._get_token_and_notify_streaming,
            symbol_resolver=self._resolve,
            profile_id_getter=self._get_profile_id,
        )

        if not lazy_auth:
            self._auth.authenticate()

        if not lazy_symbols:
            self._load_symbols()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client and disconnect streaming."""
        self.streaming.disconnect()
        self._http.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _token(self) -> str:
        """Get a valid client token, refreshing if needed."""
        return self._auth.get_client_token()

    def _get_token_and_notify_streaming(self) -> str:
        """Get a valid token and push it to StreamingClient if it changed.

        Used as the ``token_getter`` for :class:`~younit.streaming.StreamingClient`
        so that Lightstreamer always uses an up-to-date token.
        """
        token = self._auth.get_client_token()
        self.streaming.update_token(token)
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with automatic 401 refresh-and-retry.

        Args:
            method: HTTP method string.
            path: API path (appended to base_url).
            params: Query parameters.
            json: Request body dict.

        Returns:
            httpx.Response on success.

        Raises:
            Unauthorized: If refresh fails and the retry also returns 401.
            APIError subclass: On other HTTP errors.
        """
        url = f"{self._base_url}{path}"
        headers = {
            **self._default_headers,
            "Authorization": f"Bearer {self._token()}",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        response = self._http.request(method, url, headers=headers, params=params, json=json)

        if response.status_code == 401:
            # Refresh token and retry once
            new_token = self._auth.handle_401()
            headers["Authorization"] = f"Bearer {new_token}"
            response = self._http.request(method, url, headers=headers, params=params, json=json)

        raise_for_status(response)
        return response

    def _resolve(self, symbol: str) -> int:
        """Resolve a ticker to its integer stockId.

        Args:
            symbol: Ticker string (case-insensitive).

        Returns:
            Integer stockId.

        Raises:
            InvalidSymbol: If the ticker is not found.
        """
        if not self._symbols.is_loaded:
            self._load_symbols()
        return self._symbols.resolve(symbol)

    def _load_symbols(self) -> None:
        """Load the symbol cache from the API."""
        raw = _market_data.list_market_stocks(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=self._settings.default_market_id,
        )
        self._symbols.load(raw)

    def _get_profile_id(self) -> int | None:
        """Return the cached profileId, fetching it via buying_power if needed."""
        if self._cached_profile_id is not None:
            return self._cached_profile_id
        if not self._symbols.is_loaded:
            self._load_symbols()
        # Pick any stock from the symbol cache to fetch the profile_id
        symbols = self._symbols.all_symbols()
        if not symbols:
            return None
        stock_id = self._symbols.resolve(symbols[0])
        try:
            bp = _trading.get_buying_power(
                self._http,
                self._base_url,
                self._default_headers,
                token=self._token(),
                stock_id=stock_id,
                market_id=self._settings.default_market_id,
            )
            if bp.profile_id is not None:
                self._cached_profile_id = bp.profile_id
        except Exception:
            pass
        return self._cached_profile_id

    # ------------------------------------------------------------------
    # Public: symbol management
    # ------------------------------------------------------------------

    def refresh_symbols(self, market_id: int | None = None) -> None:
        """Rebuild the ticker→stockId symbol cache from the API.

        Call this if you suspect the cache is stale (e.g. after a new listing).

        Args:
            market_id: Market to refresh. Defaults to the configured default.
        """
        if market_id is not None:
            self._symbols = SymbolCache(market_id)
        self._load_symbols()

    # ------------------------------------------------------------------
    # Public: account and portfolio
    # ------------------------------------------------------------------

    @property
    def profile_id(self) -> int | None:
        """The trading profile ID for this account.

        Resolved lazily on first access (may trigger a buying_power()
        call on an arbitrary symbol from the loaded symbol cache if not
        already cached from a prior buy()/sell()/buying_power() call
        this session). Cached after first successful resolution — the
        underlying API call happens at most once per Client instance,
        since a single account has one profile_id that doesn't change
        during the session.

        Returns:
            The resolved profile_id, or None if it cannot be resolved
            (e.g. an empty symbol cache).
        """
        return self._get_profile_id()

    @property
    def security_class_snapshot_captured_at(self) -> str | None:
        """ISO-8601 UTC capture date of the ``_SecurityClassID`` enrichment
        snapshot used by :meth:`list_stocks` (``None`` if the snapshot file
        is missing).

        TEMPORARY: this whole enrichment mechanism (snapshot file +
        this property) is scaffolding meant to be deleted once
        ``list_stocks()``'s backend response includes ``_SecurityClassID``
        natively — see ``younit._security_class_snapshot``'s module
        docstring for the removal checklist.
        """
        return _security_class_snapshot.snapshot_captured_at()

    def account_info(self) -> AccountInfo:
        """Fetch the client's account information.

        Returns:
            :class:`~younit.models.account.AccountInfo` with name, email,
            mobile, investor code, and datafeed flags.

        Raises:
            APIError: On HTTP error.
            AuthError: On authentication failure.
        """
        return _account.get_account_info(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
        )

    def portfolio(self, market_id: int | None = None) -> PortfolioSummary:
        """Fetch the client's portfolio summary (cash, stocks, P&L).

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            :class:`~younit.models.portfolio.PortfolioSummary`.

        Raises:
            APIError: On HTTP error.
        """
        return _account.get_portfolio_summary(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=market_id if market_id is not None else self._settings.default_market_id,
        )

    def positions(self, market_id: int | None = None) -> list[Position]:
        """Fetch the client's current open stock positions.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.portfolio.Position` objects.
            Returns an empty list if the client has no open positions.

        Raises:
            APIError: On HTTP error.
        """
        return _account.get_stock_positions(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=market_id if market_id is not None else self._settings.default_market_id,
        )

    def position(self, symbol: str, market_id: int | None = None) -> Position | None:
        """Fetch the client's position for a specific stock.

        Args:
            symbol: EGX ticker symbol (e.g. ``"COMI"``).
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            :class:`~younit.models.portfolio.Position` if a position exists,
            or None if the client does not hold this stock.

        Raises:
            InvalidSymbol: If the ticker is not in the symbol map.
            APIError: On HTTP error.
        """
        stock_id = self._resolve(symbol)
        for pos in self.positions(market_id=market_id):
            if pos.stock_id == stock_id:
                return pos
        return None

    def positions_split(
        self, market_id: int | None = None
    ) -> tuple[list[Position], list[Position]]:
        """Return (stock_positions, fund_positions), reliably split.

        ``GetStocksPortfolio`` (the endpoint backing ``positions()``) began
        returning both stock and fund holdings in the same response as of
        2026-09-09, but with two confirmed backend bugs on fund rows:
        ``Position.is_fund`` is always ``False`` (not reliable), and
        ``Position.symbol`` is garbled (a literal ``"'"`` character, not
        usable) for funds. ``fund_positions()``/``GetPortfolioSecurities``
        remains confirmed empty for this account and is not a usable
        alternative right now.

        This method works around both bugs by cross-referencing each
        position's ``stock_id`` against the known fund_id set from
        ``list_funds()`` — the only reliable signal currently available.
        For fund positions returned here, use ``.name`` for display, NOT
        ``.symbol`` (confirmed garbled) or ``.is_fund`` (confirmed always
        ``False``).

        This is a workaround pending a backend fix — see repo notes and the
        pending message to the backend team. Once ``isFund`` is fixed
        server-side, this can likely be simplified to a straightforward
        filter on ``Position.is_fund`` directly.

        Args:
            market_id: Market identifier. Defaults to configured default.

        Returns:
            (stock_positions, fund_positions) — both ``list[Position]``,
            same model, split by the fund_id cross-reference.
        """
        fund_ids = {fund.fund_id for fund in self.list_funds(market_id)}
        all_positions = self.positions(market_id)
        stock_positions = [p for p in all_positions if p.stock_id not in fund_ids]
        fund_positions = [p for p in all_positions if p.stock_id in fund_ids]
        return stock_positions, fund_positions

    def fund_positions(self, market_id: int | None = None) -> list[FundPosition]:
        """Fetch the client's current open fund positions.

        Uses ``GET /api/portfolio/GetPortfolioSecurities``, which returns a
        combined stocks+funds list — ``GetStocksPortfolio``/``positions()``
        never returns fund rows (confirmed live). ``Fund.is_user_subscribed``
        (via ``list_funds()``) is a coarser catalog-level signal; this method
        returns real per-holding quantity/value/P&L data.

        WARNING: as of 2026-09-09, this endpoint (``GetPortfolioSecurities``)
        is confirmed live to return empty results for this account
        (``securityPositions``/``stocks``/``funds`` all ``null``), even while
        real fund holdings exist. Use :meth:`positions_split` instead until
        this is resolved backend-side.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.portfolio.FundPosition` objects.
            Returns an empty list if the client has no open fund positions.

        Raises:
            APIError: On HTTP error.
        """
        return _account.get_fund_positions(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=market_id if market_id is not None else self._settings.default_market_id,
        )

    def fund_position(self, fund_id: int, market_id: int | None = None) -> FundPosition | None:
        """Fetch the client's position for a specific fund.

        Args:
            fund_id: Internal fund identifier (``Fund.fund_id``).
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            :class:`~younit.models.portfolio.FundPosition` if a position exists,
            or None if the client does not hold this fund.

        Raises:
            APIError: On HTTP error.
        """
        for pos in self.fund_positions(market_id=market_id):
            if pos.fund_id == fund_id:
                return pos
        return None

    def buying_power(self, symbol: str) -> BuyingPower:
        """Fetch buying power and profile information for a stock.

        This is step 1 of the 3-call order placement flow. The ``profile_id``
        in the response is required when placing an order.

        Args:
            symbol: EGX ticker symbol (e.g. ``"COMI"``).

        Returns:
            :class:`~younit.models.portfolio.BuyingPower` with ``profile_id``
            and available buying power in EGP.

        Raises:
            InvalidSymbol: If the ticker is not in the symbol map.
            APIError: On HTTP error.
        """
        stock_id = self._resolve(symbol)
        bp = _trading.get_buying_power(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            stock_id=stock_id,
            market_id=self._settings.default_market_id,
        )
        if bp.profile_id is not None:
            self._cached_profile_id = bp.profile_id
        return bp

    # ------------------------------------------------------------------
    # Public: market data
    # ------------------------------------------------------------------

    def quote(self, symbol: str) -> Quote:
        """Get the current price snapshot for a stock.

        Fetches live trading parameters including last price, min/max allowed
        order prices, intraday flag, and T+1 settlement flag.

        Args:
            symbol: EGX ticker symbol (e.g. ``"COMI"`` for Commercial Intl Bank).

        Returns:
            :class:`~younit.models.market_data.Quote` with price in EGP.

        Raises:
            InvalidSymbol: If the ticker is not found.
            APIError: On HTTP error.
        """
        stock_id = self._resolve(symbol)
        return _market_data.get_stock_trading_info(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=self._settings.default_market_id,
            stock_id=stock_id,
            symbol=symbol.upper(),
        )

    def stock_info(self, symbol: str) -> Quote:
        """Get detailed trading information for a stock.

        Alias for :meth:`quote`. Returns the same data including
        price limits needed for limit order validation.

        Args:
            symbol: EGX ticker symbol.

        Returns:
            :class:`~younit.models.market_data.Quote`.
        """
        return self.quote(symbol)

    def top_gainers(self, market_id: int | None = None, limit: int = 10) -> list[StockInfo]:
        """Get the top gaining stocks for a market.

        Confirmed with the backend team this is not a dedicated server-side
        computation and may return incomplete or stale data. For live,
        accurate rankings computed the same way the official app does it,
        see :meth:`get_top_movers`.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).
            limit: Maximum number of stocks to return.

        Returns:
            List of :class:`~younit.models.market_data.StockInfo` (stock metadata
            only — the API does not include price or change data in this response).
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        gainers, _ = _market_data.get_top_gainers_losers(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=mid,
            limit=limit,
        )
        return gainers

    def top_losers(self, market_id: int | None = None, limit: int = 10) -> list[StockInfo]:
        """Get the top losing stocks for a market.

        Confirmed with the backend team this is not a dedicated server-side
        computation and may return incomplete or stale data. For live,
        accurate rankings computed the same way the official app does it,
        see :meth:`get_top_movers`.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).
            limit: Maximum number of stocks to return.

        Returns:
            List of :class:`~younit.models.market_data.StockInfo` (stock metadata
            only — the API does not include price or change data in this response).
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        _, losers = _market_data.get_top_gainers_losers(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=mid,
            limit=limit,
        )
        return losers

    def trending_stocks(self, market_id: int | None = None) -> list[StockInfo]:
        """Get the trending stocks for a market.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.market_data.StockInfo`.
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        return _market_data.get_trending_stocks(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=mid,
        )

    def list_stocks(self, market_id: int | None = None) -> list[StockInfo]:
        """List ALL securities registered on a market.

        Returns every security registered on this market — common stocks,
        bonds, sukuk, and delisted rights issues alike (506 items for market
        1, confirmed via live testing) — not just actively-tradeable stocks.
        Each result is enriched with ``security_class_name`` (instrument
        type, e.g. ``"LocalSecurity_IN"``/``"OTC"``/``"Tbills"`` — see
        :data:`~younit.enums.SECURITY_CLASS_NAMES`) and
        ``is_same_day_eligible`` (live Intraday-list membership — see that
        field's docstring on :class:`~younit.models.market_data.StockInfo`
        for why it can't be inferred from ``security_class_name`` alone).

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.market_data.StockInfo`.
        """
        # market_id=None resolves to default_market_id (1 = EGX). The parameter
        # is kept for future multi-market support, but only EGX is meaningful today.
        mid = market_id if market_id is not None else self._settings.default_market_id
        raw = _market_data.list_market_stocks(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=mid,
        )
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            if "stockId" not in item and "id" in item:
                item["stockId"] = item["id"]
            if "stockName" not in item and "name" in item:
                item["stockName"] = item["name"]
            if "symbol" not in item:
                reuter = item.get("reuterCode") or ""
                item["symbol"] = reuter.split(".")[0] or None
            result.append(StockInfo.model_validate(item))
        self._enrich_security_classes(result)
        same_day_ids = self._fetch_same_day_eligible_stock_ids(mid)
        for stock in result:
            stock.is_same_day_eligible = stock.stock_id in same_day_ids
        return result

    def _fetch_same_day_eligible_stock_ids(self, market_id: int) -> set[int]:
        """Live Intraday-list membership (same-day/T0 eligible stock_ids).

        Category id is looked up dynamically via ``stock-lists-types/
        {marketId}`` (matched by name, case-insensitive "intraday"
        substring) rather than hardcoded, since "Type always equals Id" is
        only confirmed for the categories that exist today, not guaranteed
        permanently. Returns an empty set (logged) if the category can't
        be found, rather than raising.
        """
        categories = _market_data.get_stock_list_types(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=market_id,
        )
        category = next(
            (row for row in categories if "intraday" in (row.get("name") or "").lower()), None
        )
        if category is None:
            _log.warning("list_stocks_same_day_category_not_found", market_id=market_id)
            return set()

        stocks = _market_data.get_stocks_by_list_type(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            list_type=category["type"],
            list_id=category["id"],
            market_id=market_id,
        )
        return {stock.stock_id for stock in stocks if stock.stock_id is not None}

    @staticmethod
    def _enrich_security_classes(stocks: list[StockInfo]) -> None:
        """TEMPORARY: fill in security_class_id/security_class_name from the
        point-in-time snapshot (see ``younit._security_class_snapshot``'s
        removal checklist). Mutates each StockInfo in place."""
        for stock in stocks:
            class_id, class_name = _security_class_snapshot.get_security_class(stock.stock_id)
            stock.security_class_id = class_id
            stock.security_class_name = class_name

    def list_by_class(self, *class_names: str) -> list[StockInfo]:
        """Filter :meth:`list_stocks` by one or more ``security_class_name``
        values (e.g. ``"OTC"``, ``"Tbills"``, ``"LocalSecurity_IN"``). See
        :data:`~younit.enums.SECURITY_CLASS_NAMES` for all known values.

        Args:
            *class_names: One or more ``security_class_name`` values to
                include (OR logic — a stock matching ANY of them is
                included).

        Returns:
            ``list[StockInfo]`` whose ``security_class_name`` is in
            ``class_names``. Stocks with ``security_class_name=None`` (not
            in the snapshot) are never included.

        Raises:
            ValueError: If any ``class_names`` value isn't a recognized
                name (checked against
                :data:`~younit.enums.SECURITY_CLASS_NAMES`'s values,
                case-sensitive) — fails fast on a typo rather than silently
                returning an empty list.
        """
        known = set(SECURITY_CLASS_NAMES.values())
        unknown = [name for name in class_names if name not in known]
        if unknown:
            raise ValueError(
                f"Unrecognized security_class_name value(s): {unknown}. "
                "See younit.enums.SECURITY_CLASS_NAMES for valid values."
            )
        wanted = set(class_names)
        return [s for s in self.list_stocks() if s.security_class_name in wanted]

    def list_same_day_eligible(self) -> list[StockInfo]:
        """Stocks eligible for same-day (T0) trading.

        Thin convenience wrapper equivalent to
        ``[s for s in list_stocks() if s.is_same_day_eligible]``.
        """
        return [s for s in self.list_stocks() if s.is_same_day_eligible]

    def list_otc(self) -> list[StockInfo]:
        """OTC-classified stocks — equivalent to ``list_by_class("OTC")``.

        Provided as a named convenience since OTC is the most
        commonly-filtered class.
        """
        return self.list_by_class("OTC")

    @staticmethod
    def security_class_names() -> list[str]:
        """All recognized ``security_class_name`` values accepted by
        :meth:`list_by_class` (e.g. ``"OTC"``, ``"Tbills"``,
        ``"LocalSecurity_IN"``), sorted alphabetically.

        Convenience wrapper around :data:`~younit.enums.SECURITY_CLASS_NAMES`
        — no API call, no ``Client`` instance needed (safe to call as
        ``Client.security_class_names()``).
        """
        return sorted(set(SECURITY_CLASS_NAMES.values()))

    def historical_prices(
        self,
        symbol: str,
        period: ChartPeriod | str = ChartPeriod.MONTH,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[HistoricalCandle]:
        """Get historical OHLCV price data for a stock.

        Calls ``GET /api/charts/GetChartingHistoricalDataFeed``.

        Args:
            symbol: EGX ticker symbol (e.g. ``"COMI"``)
            period: Look-back window. One of :class:`~younit.enums.ChartPeriod`
                (``Day``, ``Week``, ``Month``, ``Year``). Defaults to ``Month``.
            date_from: Start date in ``YYYY-MM-DD`` format (e.g. ``"2026-06-05"``).
            date_to: End date in ``YYYY-MM-DD`` format (e.g. ``"2026-06-30"``).

        Returns:
            List of :class:`~younit.models.market_data.HistoricalCandle` objects,
            oldest first.

        Raises:
            InvalidSymbol: If the ticker is not found.
            APIError: On HTTP error.
        """
        stock_id = self._resolve(symbol)
        period_str = period.value if isinstance(period, ChartPeriod) else str(period)
        return _market_data.get_historical_prices(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            security_id=stock_id,
            period=period_str,
            date_from=date_from,
            date_to=date_to,
        )

    def search_stocks(self, query: str) -> list[StockInfo]:
        """Search for stocks by ticker substring (local search over cache).

        Searches the in-memory symbol cache — no API call. Fast and offline.

        Args:
            query: Search string matched against ticker symbols (case-insensitive).

        Returns:
            List of :class:`~younit.models.market_data.StockInfo` matching the query.
        """
        matches = self._symbols.search(query)
        # Return lightweight StockInfo objects with just symbol and stock_id
        return [StockInfo.model_validate({"stockId": sid, "symbol": sym}) for sym, sid in matches]

    def market_status(self, market_id: int | None = None, timeout: float = 8.0) -> str:
        """Check whether the market is currently open or closed.

        Uses the MarketStatistics stream (``m_MarketStatus`` field) since
        no REST endpoint for market status exists (confirmed via the
        OpenAPI spec).

        IMPORTANT: the mapping used here (2=open, 3=closed) is
        empirically derived from live observation this session, NOT
        officially confirmed by the backend team. If they confirm a
        different or fuller mapping (e.g. additional states like
        pre-open auction), update ``_MARKET_STATUS_MAP`` accordingly.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).
            timeout: Max seconds to wait for a stream update before
                giving up. Event-driven, not a fixed sleep — returns
                as soon as the first update arrives, up to this cap.

        Returns:
            ``"open"`` or ``"closed"`` if a recognized status code (2 or 3)
            arrives in time.
            ``"unknown"`` if a status code arrives but isn't recognized
            (e.g. a new/undocumented state).
            ``"unreachable"`` if no update arrives at all within timeout
            (stream didn't respond — a different failure mode than
            ``"unknown"``, worth distinguishing for debugging).
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        received = threading.Event()
        status_holder: dict[str, str | None] = {"status": None}

        def _on_update(update: MarketUpdate) -> None:
            if not received.is_set():
                status_holder["status"] = update.status
                received.set()

        def _on_error(_exc: Exception) -> None:
            received.set()

        sub = self.streaming.subscribe_market(
            market_id=mid,
            on_update=_on_update,
            on_error=_on_error,
        )
        try:
            arrived = received.wait(timeout=timeout)
        finally:
            self.streaming.unsubscribe(sub)

        if not arrived:
            return "unreachable"
        return _MARKET_STATUS_MAP.get(status_holder["status"] or "", "unknown")

    def get_top_movers(
        self,
        limit: int = 50,
        market_id: int | None = None,
        timeout: float = 10.0,
    ) -> list[TopMover]:
        """Get current top gainers/losers, computed via live snapshot bursts.

        Subscribes to SymbolStatistics for the FULL real-equity universe
        (via :meth:`list_stocks`, filtered to ``security_class_name`` in
        ``LocalSecurity_IN``/``LocalSecurity_OUT``/``OTC`` — real equities
        only, excluding Tbills, bonds, futures, etc. which have no
        meaningful ``change_pct``/gainer-loser concept — never truncated),
        in consecutive batches of up to ``limit`` concurrent subscriptions
        at a time: captures each symbol's first snapshot event,
        unsubscribes the batch, then moves on to the next batch — a quick
        burst per batch (confirmed via live testing: 20 symbols in ~0.25s),
        not a long-running session. This mirrors exactly how the official
        EFG app computes top movers (confirmed with the backend team) — it
        is NOT a dedicated backend endpoint. See
        :meth:`top_gainers`/:meth:`top_losers` for the cheaper, one-shot
        (but potentially stale or incomplete) REST alternative.

        The initial snapshot alone was confirmed via live testing to reliably
        carry real change/change_pct data (``isSnapshot() == True``), so
        staying subscribed and waiting for a live update — this method's
        predecessor's approach — is unnecessary and avoids the
        long-running-streaming-session reliability gap found elsewhere in
        this SDK's testing (see repo notes).

        NOTE: not yet verified outside market hours — snapshot change-data
        availability when the market is closed is unconfirmed.

        Args:
            limit: Max concurrent SymbolStatistics subscriptions open at
                once — matching the SDK's own documented streaming
                concurrency guidance (proposed per-user caps of 10/30/50 by
                tier). Defaults to 50. NOT "how many stocks to sample" — the
                full real-equity universe is always covered regardless of
                this value; it only controls batch size, trading off speed
                (bigger batches = fewer round trips = faster) against
                concurrent load (bigger batches = more simultaneous
                subscriptions at once).
            market_id: Market identifier. Defaults to configured default.
            timeout: Max seconds to wait for all snapshots in EACH batch
                before moving on — applies independently per batch, not to
                the whole run; one batch's stragglers never block later
                batches from running.

        Returns:
            ``list[TopMover]`` covering the full real-equity universe,
            sorted by ``change_pct`` descending (gainers first, losers
            last). May be shorter than the true universe count if some
            batch(es) had symbols whose snapshots didn't arrive within
            ``timeout``.
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        stocks = [
            s
            for s in self.list_stocks(market_id=mid)
            if s.symbol and s.security_class_name in _TOP_MOVERS_ELIGIBLE_CLASSES
        ]

        results: list[TopMover] = []
        for start in range(0, len(stocks), limit):
            batch = stocks[start : start + limit]
            results.extend(self._snapshot_batch(batch, timeout=timeout))

        return sorted(results, key=lambda m: m.change_pct or 0.0, reverse=True)

    def _snapshot_batch(self, stocks: list[StockInfo], timeout: float) -> list[TopMover]:
        """Subscribe to one batch of symbols, capture each's first snapshot, unsubscribe.

        Helper for :meth:`get_top_movers` — never opens more than
        ``len(stocks)`` concurrent SymbolStatistics subscriptions at once.
        """
        lock = threading.Lock()
        latest: dict[str, TopMover] = {}
        all_arrived = threading.Event()
        if not stocks:
            all_arrived.set()

        def _make_callback(
            symbol: str, fallback_name: str | None
        ) -> Callable[[SymbolUpdate], None]:
            def _on_symbol_update(update: SymbolUpdate) -> None:
                with lock:
                    if symbol in latest:
                        return  # only the first snapshot counts in burst mode
                    latest[symbol] = TopMover(
                        stock_id=update.stock_id,
                        symbol=symbol,
                        name=update.name or fallback_name,
                        last=update.last,
                        change=update.change,
                        change_pct=update.change_pct,
                    )
                    if len(latest) >= len(stocks):
                        all_arrived.set()

            return _on_symbol_update

        # Fire off all subscriptions in this batch up front (not
        # one-at-a-time) so snapshots arrive concurrently rather than
        # sequentially.
        subs: list[Subscription] = [
            self.streaming.subscribe_quote(
                stock.symbol, on_update=_make_callback(stock.symbol, stock.name)
            )
            for stock in stocks
        ]

        all_arrived.wait(timeout=timeout)

        for sub in subs:
            self.streaming.unsubscribe(sub)

        with lock:
            return list(latest.values())

    # ------------------------------------------------------------------
    # Public: trading
    # ------------------------------------------------------------------


    def buy(
        self,
        symbol: str,
        qty: int,
        limit: float | None = None,
        expire: str = "day",
        expire_date: datetime | None = None,
        confirm: bool = True,
        confirm_timeout: float = 10.0,
    ) -> Order:
        """Place a buy order for a stock.

        Convenience wrapper around :meth:`place_order`. Automatically calls
        :meth:`buying_power` to get the required ``profileId``.

        For limit orders, the price is validated against the stock's allowed
        range from :meth:`quote` before submission.

        Args:
            symbol: EGX ticker symbol (e.g. ``"COMI"``).
            qty: Number of shares to buy (must be positive integer).
            limit: Limit price in EGP. If None, places a market order.
            expire: Expiry type: ``"day"`` (default) or ``"gtd"`` (Good Till Date).
                Ignored for market orders (see ``expire_date`` below).
            expire_date: Required if ``expire="gtd"`` for limit orders. For
                market orders (``limit=None``), this is now auto-set to the
                current moment (Africa/Cairo local) when not provided —
                callers no longer need to pass ``expire="gtd"`` manually for
                market orders.
            confirm: If True (the default), also resolves the real order
                status via :meth:`list_orders` immediately after placement —
                a small, scoped call (confirmed live to return only a
                handful of current/recent rows for this account, NOT a full
                account history dump), not a stream wait, since the real
                ``order_id`` is now always populated regardless of this flag
                (see :meth:`place_order`). ``list_orders()``'s ``Status`` is
                a string (e.g. ``"Accepted"``), so it's surfaced as the
                ``Order.status_text`` extra attribute (not the typed ``int``
                ``.status`` field, which stays ``None`` here — that field's
                numeric codes are unconfirmed). If the placed order isn't
                found in :meth:`list_orders`'s result (rare, e.g. a brief
                propagation lag), falls back to the lightweight stub with
                ``.status_text`` unset. Pass ``confirm=False`` to skip this
                extra call and get the lightweight stub immediately.
            confirm_timeout: Unused for order-id resolution now that it's
                returned directly by the placement response; kept for
                backward compatibility.

        Returns:
            :class:`~younit.models.orders.Order` with the placed order details.

        Raises:
            InvalidSymbol: If the ticker is not found.
            InsufficientFunds: If buying power is insufficient.
            InvalidOrder: If the limit price is outside the allowed range.
            OrderRejected: If the exchange rejects the order.
            APIError: On HTTP error.
        """
        return self.place_order(
            symbol=symbol,
            qty=qty,
            operation=OperationType.BUY,
            limit=limit,
            expire=expire,
            expire_date=expire_date,
            confirm=confirm,
            confirm_timeout=confirm_timeout,
        )

    def buy_market(
        self, symbol: str, qty: int, *, confirm: bool = True, confirm_timeout: float = 10.0
    ) -> Order:
        """Place a market buy order.

        Convenience wrapper for ``buy(limit=None)``. For full control (e.g.
        limit orders, custom expiry), use :meth:`buy` or :meth:`place_order`.

        ``confirm`` defaults to True: see :meth:`buy` for what that does and
        does not resolve (order_id yes, real status no).
        """
        return self.buy(symbol, qty, limit=None, confirm=confirm, confirm_timeout=confirm_timeout)

    def buy_limit(
        self,
        symbol: str,
        qty: int,
        price: float,
        *,
        expire: str = "day",
        expire_date: datetime | None = None,
        confirm: bool = True,
        confirm_timeout: float = 10.0,
    ) -> Order:
        """Place a limit buy order.

        Convenience wrapper for ``buy(limit=price)``. For full control, use
        :meth:`buy` or :meth:`place_order`.

        ``confirm`` defaults to True: see :meth:`buy` for what that does and
        does not resolve (order_id yes, real status no).
        """
        return self.buy(
            symbol,
            qty,
            limit=price,
            expire=expire,
            expire_date=expire_date,
            confirm=confirm,
            confirm_timeout=confirm_timeout,
        )

    def sell(
        self,
        symbol: str,
        qty: int,
        limit: float | None = None,
        expire: str = "day",
        expire_date: datetime | None = None,
        confirm: bool = True,
        confirm_timeout: float = 10.0,
        settlement: str = "t2",
    ) -> Order:
        """Place a sell order for a stock.

        Convenience wrapper around :meth:`place_order`. Automatically calls
        :meth:`buying_power` to get the required ``profileId``.

        Args:
            symbol: EGX ticker symbol (e.g. ``"COMI"``).
            qty: Number of shares to sell (must be positive integer).
            limit: Limit price in EGP. If None, places a market order.
            expire: Expiry type: ``"day"`` (default) or ``"gtd"`` (Good Till Date).
                Ignored for market orders (see ``expire_date`` below).
            expire_date: Required if ``expire="gtd"`` for limit orders. For
                market orders (``limit=None``), this is now auto-set to the
                current moment (Africa/Cairo local) when not provided —
                callers no longer need to pass ``expire="gtd"`` manually for
                market orders.
            confirm: If True (the default), also resolves the real order
                status via :meth:`list_orders` immediately after placement —
                a small, scoped call (confirmed live to return only a
                handful of current/recent rows for this account, NOT a full
                account history dump), not a stream wait, since the real
                ``order_id`` is now always populated regardless of this
                flag. ``list_orders()``'s ``Status`` is a string (e.g.
                ``"Accepted"``), so it's surfaced as the ``Order.status_text``
                extra attribute (not the typed ``int`` ``.status`` field,
                which stays ``None`` here — that field's numeric codes are
                unconfirmed). If the placed order isn't found in
                :meth:`list_orders`'s result (rare, e.g. a brief propagation
                lag), falls back to the lightweight stub with
                ``.status_text`` unset. Pass ``confirm=False`` to skip this
                extra call and get the lightweight stub immediately.
            confirm_timeout: Unused for order-id resolution now that it's
                returned directly by the placement response; kept for
                backward compatibility.
            settlement: Settlement timing for the sell, as a friendly string
                (same convention as ``expire``): ``"t2"`` (default, normal
                settlement, :attr:`~younit.enums.OperationType.SELL`),
                ``"t0"`` or its alias ``"same_day"`` (closes a position
                bought the same day, :attr:`~younit.enums.OperationType.SELL_SAME_DAY`),
                or ``"t1"`` (T+1 settlement, :attr:`~younit.enums.OperationType.SELL_T1`).

        Returns:
            :class:`~younit.models.orders.Order` with the placed order details.

        Raises:
            InvalidSymbol: If the ticker is not found.
            InvalidOrder: If the limit price is outside the allowed range, or
                ``settlement`` is not one of the valid options above.
            OrderRejected: If the exchange rejects the order.
            APIError: On HTTP error.
        """
        try:
            operation_type = _SETTLEMENT_TO_OPERATION_TYPE[settlement]
        except KeyError:
            from younit.exceptions import InvalidOrder

            raise InvalidOrder(
                f"Invalid settlement {settlement!r}. Valid options: "
                "'t2', 't0' (or 'same_day'), 't1'."
            ) from None

        return self.place_order(
            symbol=symbol,
            qty=qty,
            operation=operation_type,
            limit=limit,
            expire=expire,
            expire_date=expire_date,
            confirm=confirm,
            confirm_timeout=confirm_timeout,
        )

    def sell_market(
        self,
        symbol: str,
        qty: int,
        *,
        settlement: str = "t2",
        confirm: bool = True,
        confirm_timeout: float = 10.0,
    ) -> Order:
        """Place a market sell order.

        Convenience wrapper for ``sell(limit=None)``. For full control, use
        :meth:`sell` or :meth:`place_order`.

        ``confirm`` defaults to True: see :meth:`sell` for what that does and
        does not resolve (order_id yes, real status no).
        """
        return self.sell(
            symbol,
            qty,
            limit=None,
            settlement=settlement,
            confirm=confirm,
            confirm_timeout=confirm_timeout,
        )

    def sell_limit(
        self,
        symbol: str,
        qty: int,
        price: float,
        *,
        settlement: str = "t2",
        expire: str = "day",
        expire_date: datetime | None = None,
        confirm: bool = True,
        confirm_timeout: float = 10.0,
    ) -> Order:
        """Place a limit sell order.

        Convenience wrapper for ``sell(limit=price)``. For full control, use
        :meth:`sell` or :meth:`place_order`.

        ``confirm`` defaults to True: see :meth:`sell` for what that does and
        does not resolve (order_id yes, real status no).
        """
        return self.sell(
            symbol,
            qty,
            limit=price,
            settlement=settlement,
            expire=expire,
            expire_date=expire_date,
            confirm=confirm,
            confirm_timeout=confirm_timeout,
        )

    def place_order(
        self,
        symbol: str,
        qty: int,
        operation: OperationType,
        limit: float | None = None,
        expire: str = "day",
        expire_date: datetime | None = None,
        confirm: bool = True,
        confirm_timeout: float = 10.0,
    ) -> Order:
        """Place an order with full explicit control.

        Implements the 3-call order placement flow:
        1. Call buying_power to get profileId
        2. (Limit orders only) Call quote to validate price within allowed range
        3. POST /api/v1/orders/normal

        As of a backend change request (confirmed live 2026-09-02),
        ``POST /api/v1/orders/normal`` now returns the real order ID directly
        in the response body (nested under ``data``: ``{"result": true,
        "orderId": 54250949}``). This method therefore always returns an
        ``Order`` stub with the real ``order_id`` populated, regardless of
        ``confirm``.

        ``confirm`` defaults to True: it additionally resolves the REAL
        order status via :meth:`list_orders` immediately after placement —
        a small, scoped call, not a stream wait, since ``order_id`` is
        already known from the placement response. ``get_order()`` was used
        here previously, but is confirmed unsuitable for this purpose: its
        response has NO status field at all (structurally absent from
        ``GetOrderInfo``'s OpenAPI schema), so even on success ``.status``
        would always come back ``None`` — trying it added no value.
        ``list_orders()`` (``POST /core-services/Orders``) was live-verified
        (2026-09-10) to be a small, SCOPED call — 2 rows for this account's
        current/recent orders, NOT a full unfiltered history dump like
        ``order_history()``'s 101 rows for the same account — so it's safe
        to call unconditionally on every ``confirm=True`` placement, unlike
        ``order_history()`` would have been. ``list_orders()``'s ``Status``
        is a string (e.g. ``"Accepted"``), incompatible with the typed
        ``int`` ``Order.status`` field (unconfirmed numeric codes), so it's
        surfaced instead as a NEW, non-schema ``Order.status_text`` extra
        attribute (see ``Order``'s ``extra="allow"`` config), alongside
        ``.average_price`` (fill average) also as an extra attribute. If the
        order_id isn't found in ``list_orders()``'s result (rare, e.g. a
        brief propagation lag before it appears), falls back to the plain
        stub, same as before — never raises. Pass ``confirm=False`` to skip
        this extra call and get the lightweight stub immediately.

        Args:
            symbol: EGX ticker symbol.
            qty: Number of shares (positive integer).
            operation: :class:`~younit.enums.OperationType` (BUY or SELL).
            limit: Limit price in EGP. None = market order.
            expire: ``"day"`` or ``"gtd"``. Ignored for market orders (see
                ``expire_date`` below).
            expire_date: Required for ``"gtd"`` limit orders. For market
                orders (``limit=None``), this is now auto-set to the current
                moment (Africa/Cairo local) when not provided, regardless of
                ``expire`` — callers no longer need to pass ``expire="gtd"``
                manually for market orders.
            confirm: If True (the default), also resolve the real order
                status via :meth:`list_orders` immediately after placement
                (see caveat above about ``.status_text`` being an extra
                attribute, not the typed ``.status`` field).
            confirm_timeout: Unused for order-id resolution now that it's
                returned directly by the placement response; kept for
                backward compatibility.

        Returns:
            :class:`~younit.models.orders.Order`.

        Raises:
            InvalidSymbol: Ticker not found.
            InvalidOrder: Price out of allowed range, or GTD without expire_date.
            InsufficientFunds: Not enough buying power.
            OrderRejected: Exchange rejected the order.
            APIError: HTTP error.
            httpx.TimeoutException: Timeout — check list_orders to verify if placed.
        """
        from younit.exceptions import InvalidOrder

        if qty <= 0:
            raise InvalidOrder(f"qty must be a positive integer, got {qty}")
        # Market orders (limit=None) auto-supply expire_date below regardless
        # of `expire`, so this validation only applies to limit orders.
        if expire == "gtd" and expire_date is None and limit is not None:
            raise InvalidOrder("expire_date is required when expire='gtd'")

        stock_id = self._resolve(symbol)

        # Step 1: Get profileId from buying_power
        bp = _trading.get_buying_power(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            stock_id=stock_id,
            market_id=self._settings.default_market_id,
        )
        profile_id = bp.profile_id
        if profile_id is None:
            from younit.exceptions import InvalidOrder
            raise InvalidOrder(
                f"Buying power response for {symbol!r} did not include a profileId. "
                "The stock may not be available for trading on this profile."
            )
        self._cached_profile_id = profile_id

        # Step 2 (limit orders only): Validate price against allowed range
        if limit is not None:
            q = _market_data.get_stock_trading_info(
                self._http,
                self._base_url,
                self._default_headers,
                token=self._token(),
                market_id=self._settings.default_market_id,
                stock_id=stock_id,
            )
            if q.min_price > 0 and limit < q.min_price:
                raise InvalidOrder(
                    f"Limit price {limit} EGP is below the minimum allowed "
                    f"price {q.min_price} EGP for {symbol}."
                )
            if q.max_price > 0 and limit > q.max_price:
                raise InvalidOrder(
                    f"Limit price {limit} EGP exceeds the maximum allowed "
                    f"price {q.max_price} EGP for {symbol}."
                )

        # Build order request.
        # Market orders require a distinct set of values from limit orders,
        # confirmed by the backend team + a live test: orderExpireTermsID=2
        # (OrderExpireTerm.UNKNOWN_2, not DAY=7) and an explicit price=0 (not
        # None). executionInstructionId/isEdit are dropped entirely for market
        # orders in OrderRequest.to_api_dict(). Limit orders are unaffected.
        is_market = limit is None
        if is_market:
            order_price: float | None = 0.0
            expire_term = OrderExpireTerm.UNKNOWN_2
            # Market orders always include a same-moment expire_date now,
            # matching the one confirmed-working live example (a market sell
            # with an explicit expireDate) — auto-supplied regardless of
            # `expire`, so callers no longer need to pass expire="gtd" +
            # expire_date manually for market orders.
            if expire_date is None:
                expire_date = datetime.now(_CAIRO_TZ)
        else:
            order_price = limit
            if operation == OperationType.SELL_SAME_DAY:
                # Confirmed live 2026-09-29: same-day settlement limit sells
                # reject both DAY(7) ("...must be 'Valid Till Date'") and
                # GOOD_TILL_DATE(8) ("Market not allow Expiry Term:
                # GoodTillTime") — UNKNOWN_2 is the value that's actually
                # accepted here, same as market orders, with no expireDate
                # needed. t1/t2 limit sells are unaffected (keep DAY/GTD).
                expire_term = OrderExpireTerm.UNKNOWN_2
            else:
                expire_term = (
                    OrderExpireTerm.GOOD_TILL_DATE if expire == "gtd" else OrderExpireTerm.DAY
                )

        request = OrderRequest(
            profileID=profile_id,
            stockID=stock_id,
            operationType=operation,
            quantity=qty,
            price=order_price,
            orderExpireTermsID=expire_term,
            expireDate=expire_date,
            isMarketPrice=is_market,
        )

        # Step 3: Place the order (never retried).
        # POST /api/v1/orders/normal now returns the real orderId directly in
        # the response body (confirmed live 2026-09-02: {"messages": [...],
        # "status": 1, "data": {"result": true, "orderId": 54250949}}) — no
        # more ActiveOrders-stream-then-list_orders polling needed to resolve it.
        try:
            order_id = _orders.place_order(
                self._http,
                self._base_url,
                self._default_headers,
                token=self._token(),
                request=request,
            )
        except OrderRejected as exc:
            next_day = _parse_next_working_day(str(exc))
            if next_day is None or expire == "gtd":
                raise
            # Outside market hours: auto-retry as GTD with the exchange-supplied date.
            _log.info("order_retrying_as_gtd", next_working_day=str(next_day))
            request = OrderRequest(
                profileID=profile_id,
                stockID=stock_id,
                operationType=operation,
                quantity=qty,
                price=order_price,
                # Market orders keep UNKNOWN_2 even on retry — GTD is a
                # limit-order concept only (see comment above).
                orderExpireTermsID=OrderExpireTerm.UNKNOWN_2
                if is_market
                else OrderExpireTerm.GOOD_TILL_DATE,
                expireDate=next_day,
                isMarketPrice=is_market,
            )
            order_id = _orders.place_order(
                self._http,
                self._base_url,
                self._default_headers,
                token=self._token(),
                request=request,
            )

        # Build the Order stub with the real order_id, now known immediately
        # from the placement response (previously always None here).
        stub = Order(
            order_id=order_id,
            stock_id=stock_id,
            operation_type=operation.name,
            quantity=qty,
            price=limit,
            is_market_price=is_market,
        )
        if not confirm:
            return stub

        # confirm=True (the default) always resolves the REAL order status
        # via list_orders() immediately after placement.
        #
        # get_order() was tried here previously (falling back to
        # order_history() only on failure), but that was confirmed wrong for
        # this goal: get_order()'s response has NO status field at all,
        # confirmed structurally absent from GetOrderInfo's OpenAPI schema —
        # so even when it succeeds, .status is always None. Trying it first
        # added no value on the common (still-Active) path.
        #
        # list_orders() (POST /core-services/Orders) was live-verified
        # (2026-09-10, scripts/verify_list_orders_scope.py) to be a small,
        # SCOPED call — 2 rows for this account's live/recent orders — NOT a
        # full unfiltered history dump like order_history()'s 101 rows for
        # the same account. So calling it unconditionally here (rather than
        # only as a failure fallback) is cheap, unlike order_history() would
        # have been.
        from younit.exceptions import APIError

        try:
            orders = self.list_orders(profile_id=profile_id)
        except APIError as exc:
            _log.warning(
                "order_confirmation_list_orders_failed", order_id=order_id, error=str(exc)
            )
            return stub

        for row in orders:
            if row.get("OrderId") != order_id:
                continue
            reuter_id = row.get("ReuterId")
            return Order(
                order_id=order_id,
                stock_id=row.get("StockId") if row.get("StockId") is not None else stub.stock_id,
                operation_type=row.get("OrderTypeName") or stub.operation_type,
                price=row.get("Price") if row.get("Price") is not None else stub.price,
                quantity=row.get("Quantity") if row.get("Quantity") is not None else stub.quantity,
                is_market_price=stub.is_market_price,  # not exposed by list_orders()
                filled_quantity=row.get("ExecutedQty"),
                symbol=reuter_id.split(".")[0] if reuter_id else None,
                # Extra (non-schema) field — see Order's extra="allow"
                # config. status is deliberately NOT set on the typed int
                # `status` field: list_orders()'s Status is a string (e.g.
                # "Accepted"), not the unconfirmed numeric code.
                status_text=row.get("Status"),
                average_price=row.get("Average"),
            )
        # order_id not (yet) reflected in list_orders() — e.g. brief lag.
        return stub

    def list_orders(
        self, *, profile_id: int, market_id: int | None = None, _timeout: float | None = None
    ) -> list[dict[str, Any]]:
        """List orders belonging to a trading profile.

        Calls ``POST /core-services/Orders``, which returns rows keyed by
        ``OrderId``, ``StockId``, ``ProfileId``, ``Quantity``, ``Price``, and ``Status``.

        Args:
            profile_id: The trading profile ID (see :meth:`buying_power`).
            market_id: Market identifier. Defaults to configured default (1 = EGX).
            _timeout: Per-request read timeout override (seconds). Defaults to client default.

        Returns:
            The raw order rows as dictionaries.

        Raises:
            APIError: On HTTP error.
        """
        import httpx

        url = f"{self._base_url}/core-services/Orders"
        headers = {
            **self._default_headers,
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }
        body = {
            "MarketId": market_id if market_id is not None else self._settings.default_market_id,
            "ProfileIds": [profile_id],
            "GetFixOrders": False,
        }
        kwargs: dict[str, Any] = {}
        if _timeout is not None:
            kwargs["timeout"] = httpx.Timeout(_timeout)
        response = self._http.post(url, headers=headers, json=body, **kwargs)
        raise_for_status(response)

        data: Any = response.json()
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [r for r in data["data"] if isinstance(r, dict)]
        return []

    def cancel_order(self, order_id: int, *, profile_id: int | None = None) -> bool:
        """Cancel a stock order.

        Calls ``POST /api/v1/orders/normal/{orderId}/cancel`` — the STOCK
        cancel endpoint. For fund orders, prefer :meth:`cancel_fund_order`,
        which calls the dedicated ``POST /api/v1/orders/fund/{orderId}/cancel``
        endpoint confirmed in the OpenAPI spec.

        NOTE on cross-compatibility (investigated 2026-09-02): this endpoint
        was live-tested against a real FUND order (54262884, already
        cancelled by an earlier manual test). Calling it again returned a
        state-specific error — ``BadRequest: "Can't Edit Cancelled Order."``
        — as opposed to the generic errors returned for a not-owned order
        (``"Can Not Retrieve Client Details For ClientAccProfileID..."``) or a
        wholly nonexistent order ID (``"System Error During Submission..."``).
        This confirms the backend genuinely recognized this fund order and
        its already-cancelled state through the stock cancel endpoint — the
        earlier "True" result was NOT a false positive. However, this was
        only confirmed on an already-cancelled order (no fresh fund order was
        cancelled as part of this investigation, per instructions not to
        place additional real orders).

        RECOMMENDATION: For fund orders, use :meth:`cancel_fund_order` instead
        — it is the spec-correct, dedicated endpoint. This method's
        cross-compatibility with fund orders is an observed backend behavior,
        not a documented guarantee, and should not be relied upon going
        forward.

        Resolves ``profile_id`` in tiers: the explicit argument; then the
        ``profile_id`` cached from a prior ``buying_power()``/``buy()``/``sell()``
        call this session; then auto-resolved via the :attr:`profile_id`
        property (which itself may issue a ``buying_power()`` call on an
        arbitrary symbol from the loaded symbol cache if nothing is cached
        yet). ``get_order()`` cannot supply it: the underlying
        ``GET /api/v1/orders/{orderId}/info`` response structurally never
        includes a profile identifier (confirmed against the OpenAPI spec and
        live testing), so it is not consulted here.

        Args:
            order_id: The numeric order identifier to cancel.
            profile_id: The trading profile ID. If None, resolved via the
                :attr:`profile_id` property.

        Returns:
            True if cancellation was accepted.

        Raises:
            InvalidOrder: If no profile_id could be resolved (e.g. the symbol
                cache is empty and none was passed explicitly or cached).
            OrderRejected: If the cancellation is rejected.
            APIError: On HTTP error.
        """
        if profile_id is None:
            profile_id = self.profile_id
        if profile_id is None:
            from younit.exceptions import InvalidOrder

            raise InvalidOrder(
                f"No profile_id available for order {order_id}. Call "
                "buying_power() or a prior buy()/sell() this session first, "
                "or pass profile_id explicitly."
            )

        return _orders.cancel_order(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            order_id=order_id,
            profile_id=profile_id,
        )


    def amend_order(
        self,
        order_id: int,
        *,
        profile_id: int | None = None,
        qty: int | None = None,
        price: float | None = None,
    ) -> bool:
        """Amend an existing order (change quantity and/or price).

        Resolves ``profile_id`` in tiers: the explicit argument; then the
        ``profile_id`` cached from a prior ``buying_power()``/``buy()``/``sell()``
        call this session; then auto-resolved via the :attr:`profile_id`
        property (which itself may issue a ``buying_power()`` call on an
        arbitrary symbol from the loaded symbol cache if nothing is cached
        yet). ``get_order()`` cannot supply it: the underlying
        ``GET /api/v1/orders/{orderId}/info`` response structurally never
        includes a profile identifier (confirmed against the OpenAPI spec and
        live testing), so it is not consulted here.

        Args:
            order_id: The numeric order identifier.
            profile_id: Trading profile ID. If None, resolved via the
                :attr:`profile_id` property.
            qty: New quantity. If None, keeps current.
            price: New limit price in EGP. If None, keeps current.

        Returns:
            True if amendment was accepted.

        Raises:
            InvalidOrder: If no profile_id could be resolved (e.g. the symbol
                cache is empty and none was passed explicitly or cached).
            OrderRejected: If the amendment is rejected.
            APIError: On HTTP error.
        """
        if profile_id is None:
            profile_id = self.profile_id
        if profile_id is None:
            from younit.exceptions import InvalidOrder

            raise InvalidOrder(
                f"No profile_id available for order {order_id}. Call "
                "buying_power() or a prior buy()/sell() this session first, "
                "or pass profile_id explicitly."
            )

        return _orders.amend_order(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            order_id=order_id,
            profile_id=profile_id,
            quantity=qty,
            price=price,
        )

    def get_order(self, order_id: int) -> Order:
        """Get the current status of an order.

        Args:
            order_id: The numeric order identifier.

        Returns:
            :class:`~younit.models.orders.Order`.

        Raises:
            NotFound: If the order does not exist.
            APIError: On HTTP error.
        """
        return _orders.get_order(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            order_id=order_id,
        )

    # NOTE: The OpenAPI spec only exposes a per-profile order-history endpoint
    # (/api/stocks/order-history/{MarketId}/{ProfileId}); there is no documented
    # simple list-all-orders endpoint.

    def order_history(
        self, *, profile_id: int | None = None, market_id: int | None = None
    ) -> list[OrderHistoryEntry]:
        """Fetch historical (closed/rejected/filled) stock orders for a profile.

        Calls ``GET /api/stocks/order-history/{MarketId}/{ProfileId}`` — the
        only order-history endpoint documented in the OpenAPI spec, keyed by
        market and profile rather than a single global list-all-orders call.
        For live/pending order status, use :meth:`list_orders` or the
        ActiveOrders stream instead.

        Resolves ``profile_id`` the same way as :meth:`cancel_order`: the
        explicit argument; then the ``profile_id`` cached from a prior
        ``buying_power()``/``buy()``/``sell()`` call this session; then
        auto-resolved via the :attr:`profile_id` property.

        Args:
            profile_id: The trading profile ID. If None, resolved via the
                :attr:`profile_id` property.
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.orders.OrderHistoryEntry`.

        Raises:
            InvalidOrder: If no profile_id could be resolved.
            APIError: On HTTP error.
        """
        if profile_id is None:
            profile_id = self.profile_id
        if profile_id is None:
            from younit.exceptions import InvalidOrder

            raise InvalidOrder(
                "No profile_id available for order_history. Call buying_power() "
                "or a prior buy()/sell() this session first, or pass profile_id "
                "explicitly."
            )

        return _orders.get_order_history(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=market_id if market_id is not None else self._settings.default_market_id,
            profile_id=profile_id,
        )

    # ------------------------------------------------------------------
    # Public: funds
    # ------------------------------------------------------------------
    # list_funds()/fund()/fund_performance() below are read-only fund metadata
    # lookups. Fund order placement/amendment (buy_fund/sell_fund/
    # place_fund_order/amend_fund_order) is defined in the next section.

    def list_funds(self, market_id: int | None = None) -> list[Fund]:
        """List all mutual funds for a market.

        Args:
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.funds.Fund`.
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        return _funds.list_funds(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=mid,
        )

    def fund(self, fund_id: int, market_id: int | None = None) -> Fund:
        """Fetch details for a specific fund.

        Args:
            fund_id: Internal fund identifier.
            market_id: Market identifier. Defaults to configured default.

        Returns:
            :class:`~younit.models.funds.Fund`.

        Raises:
            NotFound: If the fund does not exist.
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        return _funds.get_fund(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            fund_id=fund_id,
            market_id=mid,
        )

    def fund_performance(
        self,
        fund_id: int,
        market_id: int | None = None,
        filter_type: int = 3,
    ) -> FundPerformance:
        """Fetch performance chart data for a fund.

        Args:
            fund_id: Internal fund identifier.
            market_id: Market identifier. Defaults to configured default.
            filter_type: Chart time range filter.
                # NOTE: The full range of valid FundChartFilterType values is
                # not currently documented.

        Returns:
            :class:`~younit.models.funds.FundPerformance`.
        """
        mid = market_id if market_id is not None else self._settings.default_market_id
        return _funds.get_fund_performance(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            fund_id=fund_id,
            market_id=mid,
            filter_type=filter_type,
        )

    def fund_order_history(
        self, *, profile_id: int | None = None, market_id: int | None = None
    ) -> list[FundOrderHistoryEntry]:
        """Fetch historical (closed/rejected/filled) fund orders for a profile.

        Calls ``GET /api/Funds/order-history/{MarketId}/{ProfileId}`` — the
        fund equivalent of :meth:`order_history` for stocks. For live/pending
        fund order status, use the ActiveOrders stream instead.

        Resolves ``profile_id`` the same way as :meth:`order_history`: the
        explicit argument; then the ``profile_id`` cached from a prior
        ``buying_power()``/``buy()``/``sell()`` call this session; then
        auto-resolved via the :attr:`profile_id` property.

        Args:
            profile_id: The trading profile ID. If None, resolved via the
                :attr:`profile_id` property.
            market_id: Market identifier. Defaults to configured default (1 = EGX).

        Returns:
            List of :class:`~younit.models.funds.FundOrderHistoryEntry`.

        Raises:
            InvalidOrder: If no profile_id could be resolved.
            APIError: On HTTP error.
        """
        if profile_id is None:
            profile_id = self.profile_id
        if profile_id is None:
            from younit.exceptions import InvalidOrder

            raise InvalidOrder(
                "No profile_id available for fund_order_history. Call buying_power() "
                "or a prior buy()/sell() this session first, or pass profile_id "
                "explicitly."
            )

        return _funds.get_fund_order_history(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            market_id=market_id if market_id is not None else self._settings.default_market_id,
            profile_id=profile_id,
        )

    # ------------------------------------------------------------------
    # Public: fund orders
    # ------------------------------------------------------------------

    def buy_fund(
        self,
        fund_id: int,
        qty: int,
        price: float,
        expire: str = "day",
        is_ipo_fund: bool = False,
        *,
        profile_id: int | None = None,
    ) -> Order:
        """Place a buy order for a fund.

        Convenience wrapper around :meth:`place_fund_order`.

        Args:
            fund_id: Internal fund identifier.
            qty: Number of fund units to buy (must be positive integer).
            price: Order price. Required — see :meth:`place_fund_order` for
                why funds have no market-order concept.
            expire: ``"day"`` (default) or ``"gtd"``. See
                :meth:`place_fund_order` for a caveat about ``"gtd"``.
            is_ipo_fund: True if this is an IPO fund subscription.
            profile_id: Trading profile ID. If None, resolved via the
                :attr:`profile_id` property.

        Returns:
            :class:`~younit.models.orders.Order` with the placed order's
            ``order_id`` populated.

        Raises:
            InvalidOrder: If qty is not positive, or no profile_id can be resolved.
            OrderRejected: If the exchange rejects the order.
            APIError: On HTTP error.
        """
        return self.place_fund_order(
            fund_id,
            qty,
            OperationType.BUY,
            price,
            expire=expire,
            is_ipo_fund=is_ipo_fund,
            profile_id=profile_id,
        )

    def sell_fund(
        self,
        fund_id: int,
        qty: int,
        price: float,
        expire: str = "day",
        is_ipo_fund: bool = False,
        *,
        profile_id: int | None = None,
    ) -> Order:
        """Place a sell order for a fund.

        Convenience wrapper around :meth:`place_fund_order`.

        Args:
            fund_id: Internal fund identifier.
            qty: Number of fund units to sell (must be positive integer).
            price: Order price. Required — see :meth:`place_fund_order` for
                why funds have no market-order concept.
            expire: ``"day"`` (default) or ``"gtd"``. See
                :meth:`place_fund_order` for a caveat about ``"gtd"``.
            is_ipo_fund: True if this is an IPO fund subscription.
            profile_id: Trading profile ID. If None, resolved via the
                :attr:`profile_id` property.

        Returns:
            :class:`~younit.models.orders.Order` with the placed order's
            ``order_id`` populated.

        Raises:
            InvalidOrder: If qty is not positive, or no profile_id can be resolved.
            OrderRejected: If the exchange rejects the order.
            APIError: On HTTP error.
        """
        return self.place_fund_order(
            fund_id,
            qty,
            OperationType.SELL,
            price,
            expire=expire,
            is_ipo_fund=is_ipo_fund,
            profile_id=profile_id,
        )

    def place_fund_order(
        self,
        fund_id: int,
        qty: int,
        operation: OperationType,
        price: float,
        expire: str = "day",
        is_ipo_fund: bool = False,
        execution_term: ExecutionTerm | None = None,
        order_via: OrderVia | None = None,
        sub_order_via: SubOrderVia | None = None,
        *,
        profile_id: int | None = None,
    ) -> Order:
        """Place a fund order with full explicit control.

        Calls ``POST /api/v1/orders/fund`` (``CreateFundOrderRequest`` — a
        separate schema from the stock order endpoint's
        ``CreateNormalOrderRequest``).

        As confirmed by a live-tested backend example (2026-09-02, order
        54262884), the response envelope matches the stock order shape
        exactly — the real order ID is returned directly in the response
        body (nested under ``data``: ``{"result": true, "orderId":
        54262884}``). This method therefore always returns an ``Order`` stub
        with the real ``order_id`` populated, mirroring :meth:`place_order`
        for stocks — no polling or confirmation step is needed.

        Funds have no market/limit distinction (``CreateFundOrderRequest`` has
        no ``isMarketPrice`` field, unlike stocks), so ``price`` is required.
        UNCONFIRMED: the spec does not mark any field of this schema as
        required, so whether the backend truly rejects a request with no
        price has not been confirmed with the backend team — treated as
        required here until confirmed otherwise.

        The confirmed minimal working body only includes ``profileId``,
        ``fundId``, ``operationType``, ``quantity``, ``price``, and
        ``isIPOFund``. ``execution_term``, ``order_via``, and
        ``sub_order_via`` below default to ``None`` and are omitted from the
        request unless explicitly set — pass them only if a specific need for
        them is confirmed with the backend.

        UNCONFIRMED: ``CreateFundOrderRequest`` also has no ``expireDate``
        field (unlike stocks), so a ``"gtd"`` fund order cannot specify an
        actual expiry date via this SDK — flagged as needing backend
        clarification on what a fund GTD order without a date means.

        Args:
            fund_id: Internal fund identifier.
            qty: Number of fund units (positive integer).
            operation: :class:`~younit.enums.OperationType` (BUY or SELL).
            price: Order price. Required (see above).
            expire: ``"day"`` (default, omits ``orderExpireTermsID`` — matches
                the confirmed minimal body) or ``"gtd"`` (sends
                ``orderExpireTermsID=GOOD_TILL_DATE`` explicitly).
            is_ipo_fund: True if this is an IPO fund subscription.
            execution_term: :class:`~younit.enums.ExecutionTerm`. Its values
                are all UNCONFIRMED (see enums.py) — left unset (None) by
                default, matching the confirmed minimal body.
            order_via: :class:`~younit.enums.OrderVia`. Left unset (None) by
                default, matching the confirmed minimal body.
            sub_order_via: :class:`~younit.enums.SubOrderVia`. Its values are
                all UNCONFIRMED (see enums.py) — left unset (None) by default,
                same reasoning as ``execution_term``.
            profile_id: Trading profile ID. If None, resolved via the
                :attr:`profile_id` property.

        Returns:
            :class:`~younit.models.orders.Order` with the placed order's
            ``order_id`` populated.

        Raises:
            InvalidOrder: If qty is not positive, or no profile_id can be resolved.
            OrderRejected: If the exchange rejects the order.
            APIError: On HTTP error.
            httpx.TimeoutException: Timeout — surfaces directly to the caller.
        """
        from younit.exceptions import InvalidOrder

        if qty <= 0:
            raise InvalidOrder(f"qty must be a positive integer, got {qty}")

        if profile_id is None:
            profile_id = self.profile_id
        if profile_id is None:
            raise InvalidOrder(
                f"No profile_id available for fund {fund_id}. Call buying_power() "
                "or a prior buy()/sell() this session first, or pass profile_id "
                "explicitly."
            )
        self._cached_profile_id = profile_id

        # Confirmed minimal body (live-tested 2026-09-02) omits
        # orderExpireTermsID entirely for "day" orders — only send it
        # explicitly when the caller asks for "gtd".
        expire_term = OrderExpireTerm.GOOD_TILL_DATE if expire == "gtd" else None

        request = FundOrderRequest(
            profileId=profile_id,
            fundId=fund_id,
            operationType=operation,
            quantity=qty,
            price=price,
            isIPOFund=is_ipo_fund,
            executionTerm=execution_term,
            orderExpireTermsID=expire_term,
            orderVia=order_via,
            subOrderVia=sub_order_via,
        )

        order_id = _orders.place_fund_order(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            request=request,
        )

        return Order(
            order_id=order_id,
            fund_id=fund_id,
            operation_type=operation.name,
            quantity=qty,
            price=price,
        )

    def amend_fund_order(
        self,
        order_id: int,
        *,
        qty: int | None = None,
        price: float | None = None,
    ) -> bool:
        """Amend an existing fund order (change quantity and/or price).

        Calls ``PATCH /api/v1/orders/fund/{orderId}``. Unlike
        :meth:`amend_order` for stocks, no ``profileId`` is required in the
        body (per ``UpdateFundOrderRequest``), so no profile_id resolution is
        needed here.

        Args:
            order_id: The numeric fund order identifier.
            qty: New quantity. If None, keeps current.
            price: New price. If None, keeps current.

        Returns:
            True if amendment was accepted.

        Raises:
            OrderRejected: If the amendment is rejected.
            APIError: On HTTP error.
        """
        return _orders.amend_fund_order(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            order_id=order_id,
            quantity=qty,
            price=price,
        )

    def cancel_fund_order(self, order_id: int) -> bool:
        """Cancel a fund order.

        Calls ``POST /api/v1/orders/fund/{orderId}/cancel`` — a dedicated
        fund-specific cancel endpoint (confirmed in the OpenAPI spec, separate
        from :meth:`cancel_order`'s stock endpoint). Unlike
        :meth:`cancel_order`, no ``profile_id`` is needed: the endpoint takes
        no request body.

        This is the correct, recommended method for cancelling fund orders —
        prefer it over :meth:`cancel_order`.

        Args:
            order_id: The numeric fund order identifier to cancel.

        Returns:
            True if cancellation was accepted.

        Raises:
            OrderRejected: If the cancellation is rejected.
            APIError: On HTTP error.
        """
        return _orders.cancel_fund_order(
            self._http,
            self._base_url,
            self._default_headers,
            token=self._token(),
            order_id=order_id,
        )

