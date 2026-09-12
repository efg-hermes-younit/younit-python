"""Account and portfolio endpoints.

Endpoints:
- GET /api/account-utils/GetAccountInfo
- GET /api/portfolio/GetPortfolioSummary
- GET /api/portfolio/GetStocksPortfolio
- GET /api/portfolio/GetPortfolioSecurities
"""

from __future__ import annotations

from typing import Any

import httpx

from younit.http import raise_for_status
from younit.logging import get_logger
from younit.models.account import AccountInfo
from younit.models.portfolio import FundPosition, PortfolioSummary, Position

_log = get_logger(__name__)


def get_account_info(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
) -> AccountInfo:
    """Fetch the client's account information and profile list.

    Calls ``GET /api/account-utils/GetAccountInfo``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers from the SDK config.
        token: Current client bearer token.

    Returns:
        Parsed :class:`~younit.models.account.AccountInfo`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/account-utils/GetAccountInfo"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_account_info", url=url)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    # The API wraps responses in a result envelope; unwrap if present
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if data is None:
        return AccountInfo()
    return AccountInfo.model_validate(data)


def get_portfolio_summary(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> PortfolioSummary:
    """Fetch the client's portfolio summary (cash, margin, buying power).

    Calls ``GET /api/portfolio/GetPortfolioSummary``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers from the SDK config.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX). Required — omitting it causes
            the API to return all-zero balances.

    Returns:
        Parsed :class:`~younit.models.portfolio.PortfolioSummary`.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/portfolio/GetPortfolioSummary"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_portfolio_summary", url=url, market_id=market_id)
    response = http.get(url, headers=headers, params={"marketId": market_id})
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if data is None:
        return PortfolioSummary()
    return PortfolioSummary.model_validate(data)


def get_stock_positions(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> list[Position]:
    """Fetch the client's current stock holdings.

    Calls ``GET /api/portfolio/GetStocksPortfolio``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers from the SDK config.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX). Required — omitting it causes
            the API to return a null ``stocks`` list (confirmed live).

    Returns:
        List of :class:`~younit.models.portfolio.Position` objects.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/portfolio/GetStocksPortfolio"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {"MarketId": market_id}

    _log.debug("get_stock_positions", url=url, market_id=market_id)
    response = http.get(url, headers=headers, params=params)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not data:
        return []
    # Response is {stocks: [...], stocksValue: ..., currency: ...}
    stocks = data.get("stocks") if isinstance(data, dict) else data
    if not stocks or not isinstance(stocks, list):
        return []
    return [Position.model_validate(item) for item in stocks]


def get_fund_positions(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int = 1,
) -> list[FundPosition]:
    """Fetch the client's current fund holdings.

    Calls ``GET /api/portfolio/GetPortfolioSecurities``, which returns a
    combined stocks+funds list (unlike ``GetStocksPortfolio``, confirmed
    live to never return fund rows) — this filters the response down to
    ``isFund=true`` entries.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers from the SDK config.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX). Required — omitting it causes
            the API to return a null ``securityPositions`` list (confirmed
            live, same trap as ``GetStocksPortfolio``'s ``MarketId``).

    Returns:
        List of :class:`~younit.models.portfolio.FundPosition` objects.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/portfolio/GetPortfolioSecurities"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {"marketId": market_id}

    _log.debug("get_fund_positions", url=url, market_id=market_id)
    response = http.get(url, headers=headers, params=params)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not data:
        return []
    # Response is {securityPositions: [...], stocks: {...}, funds: {...}, ...}
    rows = data.get("securityPositions") if isinstance(data, dict) else data
    if not rows or not isinstance(rows, list):
        return []
    return [FundPosition.model_validate(row) for row in rows if row.get("isFund")]
