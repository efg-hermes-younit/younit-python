"""Mutual fund endpoints (read-only in v0.1).

Endpoints:
- GET /api/Funds/{marketId}                                     — list funds
- GET /api/Funds/similar-to-this/{marketId}/{id}               — similar funds
- GET /api/Funds/PerformanceChart/{marketId}/{Id}/{FundChartFilterType}  — chart
"""

from __future__ import annotations

from typing import Any

import httpx

from younit.http import raise_for_status
from younit.logging import get_logger
from younit.models.funds import Fund, FundOrderHistoryEntry, FundPerformance

_log = get_logger(__name__)


def list_funds(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> list[Fund]:
    """List all mutual funds for a market.

    Calls ``GET /api/Funds/{marketId}``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).

    Returns:
        List of :class:`~younit.models.funds.Fund`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/Funds/{market_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("list_funds", url=url, market_id=market_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, list):
        return [Fund.model_validate(item) for item in data]
    return []


def get_fund(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    fund_id: int,
    market_id: int = 1,
) -> Fund:
    """Fetch details for a specific fund.

    Uses ``GET /api/Funds/similar-to-this/{marketId}/{id}`` as a proxy to
    get fund detail (the direct fund endpoint is not documented separately).

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        fund_id: Internal fund identifier.
        market_id: Market identifier (1 = EGX).

    Returns:
        Parsed :class:`~younit.models.funds.Fund`.

    Raises:
        NotFound: If the fund does not exist.
        APIError: On HTTP error responses.
    """
    # Fetch the full list and filter — a direct GET /api/Funds/{marketId}/{id}
    # endpoint is not documented in the guides or OpenAPI spec.
    # DEFERRED: confirm with backend team whether a direct single-fund endpoint
    # exists; until then this list-and-filter approach is the only known option.
    funds = list_funds(http, base_url, default_headers, token=token, market_id=market_id)
    for fund in funds:
        if fund.fund_id == fund_id:
            return fund
    from younit.exceptions import NotFound

    raise NotFound(
        f"Fund {fund_id} not found in market {market_id}.",
        status_code=404,
    )


def get_fund_performance(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    fund_id: int,
    market_id: int = 1,
    filter_type: int = 3,
) -> FundPerformance:
    """Fetch performance chart data for a fund.

    Calls ``GET /api/Funds/PerformanceChart/{marketId}/{Id}/{FundChartFilterType}``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        fund_id: Internal fund identifier.
        market_id: Market identifier (1 = EGX).
        filter_type: Chart time range filter.
            # DEFERRED: FundChartFilterType values are undocumented; blocked on
            # backend team confirmation of the full value mapping.

    Returns:
        Parsed :class:`~younit.models.funds.FundPerformance`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/Funds/PerformanceChart/{market_id}/{fund_id}/{filter_type}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_fund_performance", url=url, fund_id=fund_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not data or not isinstance(data, list):
        return FundPerformance(fund_id=fund_id, filter_type=filter_type)
    from younit.models.funds import PerformanceDataPoint

    points = [PerformanceDataPoint.model_validate(item) for item in data]
    return FundPerformance(fund_id=fund_id, filter_type=filter_type, chart_data=points)


def get_fund_order_history(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int,
    profile_id: int,
) -> list[FundOrderHistoryEntry]:
    """Fetch the historical (closed/rejected/filled) fund orders for a profile.

    Calls ``GET /api/Funds/order-history/{MarketId}/{ProfileId}`` — the fund
    equivalent of the stock order-history endpoint
    (``get_order_history`` in ``endpoints/orders.py``).

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).
        profile_id: The trading profile ID to fetch history for.

    Returns:
        List of :class:`~younit.models.funds.FundOrderHistoryEntry`, as
        returned by the API (order not guaranteed).

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/Funds/order-history/{market_id}/{profile_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_fund_order_history", url=url, market_id=market_id, profile_id=profile_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not isinstance(data, list):
        return []
    return [FundOrderHistoryEntry.model_validate(row) for row in data if isinstance(row, dict)]
