"""MCP server entry point for the Younit Trading API.

Exposes every SDK method as an MCP tool. The LLM (Claude Desktop, Claude Code,
or any MCP client) can use these tools to:
- Fetch market data (quotes, movers, trending stocks)
- Query portfolio and account information
- Place and manage orders (when not in read-only mode)
- Query mutual funds

Safety settings (all via environment variables):
- ``EFG_MCP_READONLY=true``        — disables all write tools
- ``EFG_MCP_MAX_ORDER_VALUE_EGP``  — caps single order value in EGP
- ``EFG_MCP_MAX_DAILY_ORDERS``     — circuit breaker on daily order count
- ``EFG_SIMULATION=true``          — uses simulation environment (recommended for setup)

Start with stdio (default for Claude Desktop)::

    younit-mcp

Start with SSE (for networked deployment)::

    younit-mcp --transport sse --port 8080
"""

from __future__ import annotations

import argparse
import sys
import threading

from mcp.server.fastmcp import FastMCP

from younit.client import Client
from younit.mcp_server.safety import (
    DailyOrderCounter,
    SafetySettings,
    check_daily_limit,
    check_order_value,
)

# ---------------------------------------------------------------------------
# Server and state initialisation
# ---------------------------------------------------------------------------

app = FastMCP("younit")

# These are initialised in main() after argument parsing
_client: Client | None = None
_safety: SafetySettings | None = None
_order_counter: DailyOrderCounter = DailyOrderCounter()


def _get_client() -> Client:
    """Get the initialised SDK client."""
    if _client is None:
        raise RuntimeError("MCP server not initialised. Call main() first.")
    return _client


def _get_safety() -> SafetySettings:
    """Get the safety settings."""
    if _safety is None:
        raise RuntimeError("MCP server not initialised. Call main() first.")
    return _safety


# ---------------------------------------------------------------------------
# Read-only tools (always registered)
# ---------------------------------------------------------------------------


@app.tool()
def quote(symbol: str) -> dict:  # type: ignore[return]
    """Get the current price snapshot for an EGX-listed stock.

    Use this to get the current market price, allowed order price range
    (min/max prices in EGP), and trading flags before placing an order.

    Args:
        symbol: EGX ticker code (e.g. "COMI" for Commercial International Bank,
            "HRHO" for EFG Hermes, "ETEL" for Telecom Egypt). Always uppercase.

    Returns:
        Dict with:
        - symbol: Ticker code
        - last: Last traded price in EGP
        - min_price: Minimum allowed limit order price in EGP
        - max_price: Maximum allowed limit order price in EGP
        - change: Price change from previous close in EGP
        - change_pct: Price change as percentage
        - volume: Number of shares traded today
        - is_intraday: True if T+0 intraday trading is supported
        - is_tplus1: True if settlement is T+1
    """
    return _get_client().quote(symbol).model_dump()


@app.tool()
def account_info() -> dict:  # type: ignore[return]
    """Get the authenticated client's account information and profile list.

    Use this to retrieve the client's profile IDs, name, and sub-account details.
    Profile IDs appear in this response and are required for order placement.

    Returns:
        Dict with client profile information including profile IDs and names.
    """
    return _get_client().account_info().model_dump()


@app.tool()
def portfolio() -> dict:  # type: ignore[return]
    """Get the client's portfolio summary: cash, margin, and buying power.

    Shows available cash balances and margin details in EGP.
    Use this to check how much capital is available before placing orders.

    Returns:
        Dict with CashDetails (available/blocked/total in EGP) and
        MarginDetails, plus total portfolio value and buying power.
    """
    return _get_client().portfolio().model_dump()


@app.tool()
def positions() -> list:  # type: ignore[return]
    """Get the client's current open stock positions on EGX.

    Shows all stocks currently held, with quantity, average cost, current
    price, market value, and unrealised P&L in EGP.

    Returns:
        List of position dicts. Each includes stock_id, symbol, quantity,
        average_price (EGP), current_price (EGP), market_value (EGP),
        unrealized_pnl (EGP), unrealized_pnl_pct (%).
    """
    return [p.model_dump() for p in _get_client().positions()]


@app.tool()
def position(symbol: str) -> dict | None:  # type: ignore[return]
    """Get the client's position for a specific EGX stock.

    Args:
        symbol: EGX ticker code (e.g. "COMI"). Always uppercase.

    Returns:
        Position dict if the client holds this stock, or null if no position.
        Position includes quantity, average_price (EGP), current_price (EGP),
        market_value (EGP), unrealized_pnl (EGP).
    """
    pos = _get_client().position(symbol)
    return pos.model_dump() if pos else None


@app.tool()
def buying_power(symbol: str) -> dict:  # type: ignore[return]
    """Get buying power and profile information for a specific EGX stock.

    Returns the available buying power in EGP and the profile_id required
    for order placement. This is step 1 of the order placement workflow.

    Args:
        symbol: EGX ticker code (e.g. "COMI"). Always uppercase.

    Returns:
        Dict with profile_id (integer, required for orders), profile_name,
        buying_power (EGP, available to buy this stock), and
        certificates_quantity_held (shares currently held).
    """
    return _get_client().buying_power(symbol).model_dump()


@app.tool()
def top_gainers(market_id: int = 1, limit: int = 10) -> list:  # type: ignore[return]
    """Get the top gaining stocks on EGX today.

    Returns stocks sorted by gain percentage, descending.

    Args:
        market_id: Market identifier. 1 = EGX (Egypt Stock Exchange). Default 1.
        limit: Maximum number of stocks to return. Default 10.

    Returns:
        List of market mover dicts, each with symbol, last (EGP), change (EGP),
        change_pct (%), and volume (shares).
    """
    return [m.model_dump() for m in _get_client().top_gainers(market_id=market_id, limit=limit)]


@app.tool()
def top_losers(market_id: int = 1, limit: int = 10) -> list:  # type: ignore[return]
    """Get the top losing stocks on EGX today.

    Returns stocks sorted by loss percentage, ascending (most negative first).

    Args:
        market_id: Market identifier. 1 = EGX (Egypt Stock Exchange). Default 1.
        limit: Maximum number of stocks to return. Default 10.

    Returns:
        List of market mover dicts, each with symbol, last (EGP), change (EGP),
        change_pct (% negative for losers), and volume (shares).
    """
    return [m.model_dump() for m in _get_client().top_losers(market_id=market_id, limit=limit)]


@app.tool()
def trending_stocks(market_id: int = 1) -> list:  # type: ignore[return]
    """Get the trending stocks on EGX right now.

    Returns stocks with high recent activity or social/algorithmic momentum.

    Args:
        market_id: Market identifier. 1 = EGX (Egypt Stock Exchange). Default 1.

    Returns:
        List of stock info dicts with symbol, last price (EGP), change_pct (%),
        and volume (shares).
    """
    return [s.model_dump() for s in _get_client().trending_stocks(market_id=market_id)]


@app.tool()
def search_stocks(query: str) -> list:  # type: ignore[return]
    """Search for EGX stocks by ticker symbol substring.

    Local search over the cached symbol map — no API call, instant results.
    Useful for finding a ticker code when you know part of the company name
    abbreviation. Example: query "COM" might return "COMI" (Commercial Intl Bank).

    Args:
        query: Search string matched against EGX ticker symbols (case-insensitive).
            e.g. "COM", "EFG", "HRHO".

    Returns:
        List of matching stock info dicts with symbol and stock_id.
    """
    return [s.model_dump() for s in _get_client().search_stocks(query)]


@app.tool()
def get_order(order_id: int) -> dict:  # type: ignore[return]
    """Get the current status of an order.

    Use this to check whether a previously placed order was accepted,
    filled, partially filled, cancelled, or rejected by the exchange.

    Args:
        order_id: The numeric order identifier (integer).

    Returns:
        Dict with order_id, stock_id, operation_type (Buy/Sell), quantity (shares),
        price (EGP, null for market orders), status (integer status code),
        filled_quantity (shares), and expire_date.
    """
    return _get_client().get_order(order_id).model_dump(mode="json")


@app.tool()
def funds(market_id: int = 1) -> list:  # type: ignore[return]
    """List all available mutual funds on EGX.

    Returns information about EFG-listed mutual funds including NAV per unit
    in EGP, minimum subscription, and risk level classification.

    Args:
        market_id: Market identifier. 1 = EGX. Default 1.

    Returns:
        List of fund dicts with fund_id, name, nav (EGP per unit),
        minimum_subscription (EGP), currency, and risk_level.
    """
    return [f.model_dump(mode="json") for f in _get_client().list_funds(market_id=market_id)]


@app.tool()
def fund_performance(fund_id: int, market_id: int = 1, filter_type: int = 3) -> dict:  # type: ignore[return]
    """Get performance chart data for a mutual fund.

    Args:
        fund_id: Internal fund identifier (integer). Get from funds().
        market_id: Market identifier. 1 = EGX. Default 1.
        filter_type: Time range filter. Exact values pending backend confirmation.
            Default 3.

    Returns:
        Dict with fund_id, filter_type, and chart_data (list of date/value pairs,
        where value is NAV in EGP).
    """
    result = _get_client().fund_performance(
        fund_id=fund_id, market_id=market_id, filter_type=filter_type
    )
    return result.model_dump(mode="json")


@app.tool()
def stock_info(symbol: str) -> dict:  # type: ignore[return]
    """Get detailed trading information for a specific EGX stock.

    Returns the same data as quote() — current price, allowed limit order
    price range, and trading flags. Use this when you want to look up
    a stock's trading parameters by ticker before placing an order.

    Args:
        symbol: EGX ticker code (e.g. "COMI", "HRHO", "ETEL"). Always uppercase.

    Returns:
        Dict with symbol, last price (EGP), min_price (EGP), max_price (EGP),
        change (EGP), change_pct (%), volume (shares), is_intraday, is_tplus1.
    """
    return _get_client().stock_info(symbol).model_dump()


@app.tool()
def list_stocks(market_id: int = 1) -> list:  # type: ignore[return]
    """List all stocks available on EGX.

    Returns the complete set of listed stocks with their ticker symbols and
    internal stock IDs. Useful for discovering available tickers.

    Args:
        market_id: Market identifier. 1 = EGX (Egypt Stock Exchange). Default 1.

    Returns:
        List of stock dicts, each with stock_id (integer) and symbol (ticker string).
    """
    return [s.model_dump() for s in _get_client().list_stocks(market_id=market_id)]


@app.tool()
def historical_prices(symbol: str, period: str = "Month", date_from: str | None = None, date_to: str | None = None) -> list:  # type: ignore[return]
    """Get historical OHLCV (open/high/low/close/volume) price data for an EGX stock.

    Useful for charting, trend analysis, and building price context before
    making a trading decision.

    Args:
        symbol: EGX ticker code (e.g. "COMI"). Always uppercase.
        period: Look-back window. One of:
            - "Day"   — intraday data for today
            - "Week"  — last 7 days
            - "Month" — last 30 days (default)
            - "Year"  — last 365 days
        date_from: Start date in YYYY-MM-DD format (e.g. "2026-06-05").
        date_to: End date in YYYY-MM-DD format (e.g. "2026-06-30").

    Returns:
        List of candle dicts, oldest first. Each candle has:
        - date: ISO datetime string
        - open: Opening price in EGP
        - high: Highest price in EGP
        - low: Lowest price in EGP
        - close: Closing price in EGP
        - volume: Number of shares traded in this period
    """
    candles = _get_client().historical_prices(symbol=symbol, period=period, date_from=date_from, date_to=date_to)
    return [c.model_dump(mode="json") for c in candles]


@app.tool()
def streaming_quote(symbol: str, timeout_seconds: float = 5.0) -> dict | None:  # type: ignore[return]
    """Get a single real-time price snapshot for an EGX stock via the live feed.

    Connects to the Lightstreamer streaming feed, waits for the first live
    update, and returns it. More current than quote() which is a REST snapshot.

    Args:
        symbol: EGX ticker code (e.g. "COMI"). Always uppercase.
        timeout_seconds: How long to wait for a live update before giving up.
            Default 5 seconds. Increase if the market is illiquid.

    Returns:
        Dict with live price data (symbol, last, bid, ask, volume, change_pct, etc.)
        or null if no update was received within the timeout.
    """
    client = _get_client()
    event: threading.Event = threading.Event()
    result: list[dict] = []

    def _on_update(update: object) -> None:
        if not result:
            result.append(update.model_dump())  # type: ignore[union-attr]
            event.set()

    sub = client.streaming.subscribe_quote(symbol, on_update=_on_update)
    event.wait(timeout=timeout_seconds)
    client.streaming.unsubscribe(sub)
    return result[0] if result else None


@app.tool()
def streaming_orders(timeout_seconds: float = 5.0) -> dict | None:  # type: ignore[return]
    """Get a single real-time order status snapshot from the live order feed.

    Subscribes to the ActiveOrders Lightstreamer stream and returns the first
    order update received. Recommended after placing an order to confirm
    status without polling the REST endpoint.

    Args:
        timeout_seconds: How long to wait for an order update before giving up.
            Default 5 seconds. Returns null if no update is received.

    Returns:
        Dict with order update data (order_number, status_ui, quantity,
        executed_quantity, etc.) or null if no update within the timeout.
    """
    client = _get_client()
    event: threading.Event = threading.Event()
    result: list[dict] = []

    def _on_update(update: object) -> None:
        if not result:
            result.append(update.model_dump())  # type: ignore[union-attr]
            event.set()

    sub = client.streaming.subscribe_orders(on_update=_on_update)
    event.wait(timeout=timeout_seconds)
    client.streaming.unsubscribe(sub)
    return result[0] if result else None


# ---------------------------------------------------------------------------
# Write tools (only registered when NOT in read-only mode)
# ---------------------------------------------------------------------------


def _register_write_tools() -> None:
    """Register write tools with the MCP server.

    Called only when EFG_MCP_READONLY is False. In read-only mode, the LLM
    never sees these tools — they are not registered at all.
    """

    @app.tool()
    def buy(symbol: str, qty: int, limit: float | None = None) -> dict:  # type: ignore[return]
        """Place a buy order for an EGX-listed stock.

        Implements the full 3-call order placement flow automatically:
        fetches buying power (to get profileId), validates limit price against
        allowed range, then places the order.

        Safety controls apply:
        - EFG_MCP_MAX_ORDER_VALUE_EGP: Rejects if qty * limit exceeds cap
        - EFG_MCP_MAX_DAILY_ORDERS: Rejects if daily order count reached
        - EFG_SIMULATION: If true, order goes to paper trading environment

        Args:
            symbol: EGX ticker code (e.g. "COMI" for Commercial Intl Bank).
                Always uppercase. Use search_stocks() to find tickers.
            qty: Number of shares to buy (positive integer, e.g. 100).
            limit: Limit price in EGP (e.g. 82.5). If omitted, places a
                market order at the current ask price. For limit orders,
                the price must be within the stock's allowed range (see quote()).

        Returns:
            Dict with order details: stock_id, operation_type, quantity (shares),
            price (EGP), is_market_price.

        Raises error if:
        - Ticker not found
        - Limit price out of allowed range
        - Insufficient buying power
        - Order rejected by exchange
        - Safety limit exceeded
        """
        safety = _get_safety()
        check_order_value(qty, limit, safety)
        check_daily_limit(_order_counter, safety)
        result = _get_client().buy(symbol=symbol, qty=qty, limit=limit)
        _order_counter.increment()
        return result.model_dump(mode="json")

    @app.tool()
    def sell(symbol: str, qty: int, limit: float | None = None) -> dict:  # type: ignore[return]
        """Place a sell order for an EGX-listed stock.

        Implements the full 3-call order placement flow automatically.

        Safety controls apply:
        - EFG_MCP_MAX_ORDER_VALUE_EGP: Rejects if qty * limit exceeds cap
        - EFG_MCP_MAX_DAILY_ORDERS: Rejects if daily order count reached
        - EFG_SIMULATION: If true, order goes to paper trading environment

        Args:
            symbol: EGX ticker code (e.g. "COMI"). Always uppercase.
                The client must hold this stock to sell it.
            qty: Number of shares to sell (positive integer). Cannot exceed
                the quantity held (see position()).
            limit: Limit price in EGP. If omitted, places a market sell
                at the current bid price.

        Returns:
            Dict with order details: stock_id, operation_type, quantity (shares),
            price (EGP), is_market_price.
        """
        safety = _get_safety()
        check_order_value(qty, limit, safety)
        check_daily_limit(_order_counter, safety)
        result = _get_client().sell(symbol=symbol, qty=qty, limit=limit)
        _order_counter.increment()
        return result.model_dump(mode="json")

    @app.tool()
    def cancel_order(order_id: int) -> dict:  # type: ignore[return]
        """Cancel an open order.

        Only open (pending/active) orders can be cancelled. Already-filled
        or expired orders cannot be cancelled.

        Args:
            order_id: The numeric order identifier (integer).
                Get this from the response of buy(), sell(), or get_order().

        Returns:
            Dict with {"success": true} if the cancellation was accepted.
        """
        success = _get_client().cancel_order(order_id)
        return {"success": success, "order_id": order_id}

    @app.tool()
    def amend_order(
        order_id: int,
        qty: int | None = None,
        price: float | None = None,
    ) -> dict:  # type: ignore[return]
        """Amend an open order (change quantity and/or limit price).

        At least one of qty or price must be provided.

        Safety controls apply:
        - EFG_MCP_MAX_ORDER_VALUE_EGP: Rejects if the resulting qty * price
          (after applying this amendment) exceeds cap — checked against the
          order's state AFTER the amendment, not its original placed value,
          so this cannot be bypassed by placing a small order and then
          amending it upward.

        Args:
            order_id: The numeric order identifier (integer).
            qty: New quantity in shares (positive integer). If omitted,
                keeps the current quantity.
            price: New limit price in EGP. If omitted, keeps the current price.

        Returns:
            Dict with {"success": true} if the amendment was accepted.
        """
        if qty is None and price is None:
            return {"success": False, "error": "At least one of qty or price must be provided."}
        client = _get_client()
        safety = _get_safety()
        current = client.get_order(order_id)
        effective_qty = qty if qty is not None else current.quantity
        effective_price = price if price is not None else current.price
        if effective_qty is not None:
            check_order_value(effective_qty, effective_price, safety)
        success = client.amend_order(order_id, qty=qty, price=price)
        return {"success": success, "order_id": order_id}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the ``younit-mcp`` console script.

    Parses transport arguments, initialises the SDK client from environment
    variables, and starts the MCP server.
    """
    global _client, _safety

    parser = argparse.ArgumentParser(
        description="Younit Trading API — MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables (required):
  EFG_PARTNER_ID         Partner identifier
  EFG_PARTNER_SECRET     Partner secret
  EFG_TRADING_UUID       Client trading UUID

Safety settings (optional):
  EFG_MCP_READONLY             true/false (default: false)
  EFG_MCP_MAX_ORDER_VALUE_EGP  integer EGP cap per order (default: 1000)
  EFG_MCP_MAX_DAILY_ORDERS     integer orders per day (default: 100)
  EFG_SIMULATION               true/false (default: false; use true for setup)
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for SSE transport (default: 8080)",
    )
    args = parser.parse_args()

    # Initialise safety settings from env vars
    _safety = SafetySettings()

    # Initialise SDK client (reads credentials from env vars)
    _client = Client()

    # Register write tools only when not in read-only mode
    if not _safety.readonly:
        _register_write_tools()
    else:
        print(
            "EFG MCP server running in READ-ONLY mode. "
            "Write tools (buy, sell, cancel, amend) are not available.",
            file=sys.stderr,
        )

    # Start the server
    if args.transport == "stdio":
        app.run(transport="stdio")
    else:
        app.settings.port = args.port
        app.run(transport="sse")


if __name__ == "__main__":
    main()
