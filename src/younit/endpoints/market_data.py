"""Market data endpoints.

Endpoints:
- GET /api/stocks/market/{marketId}           — list all stocks (used for symbol cache)
- GET /api/stocks/stock-trading-info/{marketId}/{id}  — live trading params + price
- GET /api/stocks/top-gainers-losers/{marketId}       — top gainers and losers
- GET /api/stocks/stocks-analytics/{marketId}/TrendingStocks  — trending stocks
- GET /api/stocks/stock-lists-types/{marketId}        — stock list categories (Intraday, OTC, ...)
- GET /api/stocks/stocks-by-list-type/{type}/{id}/{marketId}  — securities within a list category
"""

from __future__ import annotations

from typing import Any

import httpx

from younit.http import raise_for_status
from younit.logging import get_logger
from younit.models.market_data import HistoricalCandle, Quote, StockInfo

_log = get_logger(__name__)


def list_market_stocks(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> list[dict[str, Any]]:
    """Fetch all stocks in a market (raw dicts for symbol cache building).

    Calls ``GET /api/stocks/market/{marketId}``.

    Returns raw dicts rather than typed models so the symbol cache can
    extract ``stockId`` and ``symbol`` without needing a full model parse.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).

    Returns:
        List of raw stock dicts from the API.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/market/{market_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("list_market_stocks", url=url, market_id=market_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, list):
        return data  # type: ignore[return-value]
    return []


def get_stock_trading_info(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int,
    stock_id: int,
    symbol: str | None = None,
) -> Quote:
    """Fetch live trading parameters and current price for a stock.

    Calls ``GET /api/stocks/stock-trading-info/{marketId}/{id}``.

    Returns price limits (min/max), intraday flag, T+1 flag, and the current
    price. The min/max prices are used to validate limit order prices.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).
        stock_id: Internal stock identifier.

    Returns:
        Parsed :class:`~younit.models.market_data.Quote`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/stock-trading-info/{market_id}/{stock_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_stock_trading_info", url=url, stock_id=stock_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if data is None:
        return Quote()
    # Normalize field names from the actual API response to what Quote expects
    if isinstance(data, dict):
        data.setdefault("stockId", data.get("securityID"))
        data.setdefault("stockName", data.get("securityName"))
        data.setdefault("marketId", data.get("marketID"))
        data.setdefault("isIntraday", data.get("allowIntraDay"))
        data.setdefault("isTPlus1", data.get("allowTPlus1"))
        # Use the caller-provided symbol if available; otherwise derive from reuterID
        if symbol:
            data["symbol"] = symbol
        elif not data.get("symbol"):
            reuter = data.get("reuterID") or ""
            data["symbol"] = reuter.split(".")[0] or None
    return Quote.model_validate(data)


def get_top_gainers_losers(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
    limit: int = 10,
) -> tuple[list[StockInfo], list[StockInfo]]:
    """Fetch the top gainers and losers for a market.

    Calls ``GET /api/stocks/top-gainers-losers/{marketId}``.

    The API returns ``StockDto`` items (stock metadata only — no price or
    change data). Use :meth:`~younit.client.Client.quote` on individual
    symbols if you need live prices.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).
        limit: Maximum number of movers to return per side.

    Returns:
        Tuple of ``(gainers, losers)`` where each is a list of
        :class:`~younit.models.market_data.StockInfo`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/top-gainers-losers/{market_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_top_gainers_losers", url=url, market_id=market_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    def _parse_stock_dto_list(items: list[Any], n: int) -> list[StockInfo]:
        result = []
        for item in items[:n]:
            if not isinstance(item, dict):
                continue
            if "stockId" not in item and "id" in item:
                item["stockId"] = item["id"]
            if "symbol" not in item:
                reuter = item.get("reuterCode") or ""
                item["symbol"] = reuter.split(".")[0] or None
            if "stockName" not in item and "name" in item:
                item["stockName"] = item["name"]
            result.append(StockInfo.model_validate(item))
        return result

    gainers: list[StockInfo] = []
    losers: list[StockInfo] = []

    if isinstance(data, dict):
        raw_gainers = data.get("topGainers") or data.get("gainers") or data.get("Gainers") or []
        raw_losers = data.get("topLosers") or data.get("losers") or data.get("Losers") or []
        gainers = _parse_stock_dto_list(raw_gainers, limit)
        losers = _parse_stock_dto_list(raw_losers, limit)
    elif isinstance(data, list):
        gainers = _parse_stock_dto_list(data, limit)

    return gainers, losers


def get_trending_stocks(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> list[StockInfo]:
    """Fetch the trending stocks for a market.

    Calls ``GET /api/stocks/stocks-analytics/{marketId}/TrendingStocks``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).

    Returns:
        List of :class:`~younit.models.market_data.StockInfo`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/stocks-analytics/{market_id}/TrendingStocks"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_trending_stocks", url=url, market_id=market_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # StockDto uses "id" and "reuterCode"; normalise to the fields
        # StockInfo expects ("stockId", "symbol", "stockName").
        if "stockId" not in item and "id" in item:
            item["stockId"] = item["id"]
        if "symbol" not in item:
            reuter = item.get("reuterCode") or ""
            item["symbol"] = reuter.split(".")[0] or None
        if "stockName" not in item and "name" in item:
            item["stockName"] = item["name"]
        result.append(StockInfo.model_validate(item))
    return result


def get_historical_prices(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    security_id: int,
    period: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[HistoricalCandle]:
    """Fetch historical charting data feed for a security.

    Calls ``GET /api/charts/GetChartingHistoricalDataFeed``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        security_id: Internal stock identifier (``stockId``).
        period: Chart period string — one of ``"Day"``, ``"Week"``,
            ``"Month"``, or ``"Year"``.
        date_from: Start date in ``YYYY-MM-DD`` format (inclusive).
        date_to: End date in ``YYYY-MM-DD`` format (inclusive).

    Returns:
        List of :class:`~younit.models.market_data.HistoricalCandle` objects,
        one per time bucket, oldest first.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/charts/GetChartingHistoricalDataFeed"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {"SecurityID": security_id, "Period": period}
    if date_from is not None:
        params["DateFrom"] = date_from
    if date_to is not None:
        params["DateTo"] = date_to

    _log.debug("get_historical_prices", url=url, security_id=security_id, period=period,
               date_from=date_from, date_to=date_to)
    response = http.get(url, headers=headers, params=params)
    raise_for_status(response)

    data: Any = response.json()
    # Response shape: {"messages": ..., "data": {"errorCode": ..., "data": {"chartingDataViewModel": [...]}}}  # noqa: E501
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, dict):
        data = data.get("chartingDataViewModel") or []
    if isinstance(data, list):
        return [HistoricalCandle.model_validate(item) for item in data]
    return []


def get_stock_list_types(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> list[dict[str, Any]]:
    """Fetch the stock list categories available for a market.

    Calls ``GET /api/stocks/stock-lists-types/{marketId}``.

    Returns raw dicts (each with ``name``/``description``/``id``/``type``/
    ``count`` keys) rather than a typed model, since this is only used to
    look up category ids by name.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).

    Returns:
        List of raw category dicts from the API.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/stock-lists-types/{market_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_stock_list_types", url=url, market_id=market_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, list):
        return data  # type: ignore[return-value]
    return []


def get_stocks_by_list_type(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    list_type: int,
    list_id: int,
    market_id: int = 1,
) -> list[StockInfo]:
    """Fetch the securities belonging to a stock list category.

    Calls ``GET /api/stocks/stocks-by-list-type/{type}/{id}/{marketId}``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        list_type: Category ``type`` (from ``get_stock_list_types``).
        list_id: Category ``id`` (from ``get_stock_list_types``).
        market_id: Market identifier (1 = EGX).

    Returns:
        List of :class:`~younit.models.market_data.StockInfo`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/stocks-by-list-type/{list_type}/{list_id}/{market_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug(
        "get_stocks_by_list_type", url=url, list_type=list_type, list_id=list_id,
        market_id=market_id,
    )
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # StockDto uses "id" and "reuterCode"; normalise to the fields
        # StockInfo expects ("stockId", "symbol", "stockName").
        if "stockId" not in item and "id" in item:
            item["stockId"] = item["id"]
        if "symbol" not in item:
            reuter = item.get("reuterCode") or ""
            item["symbol"] = reuter.split(".")[0] or None
        if "stockName" not in item and "name" in item:
            item["stockName"] = item["name"]
        result.append(StockInfo.model_validate(item))
    return result
