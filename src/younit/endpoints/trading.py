"""Trading endpoints.

Endpoints:
- GET /api/v1/trading/buying-power/normal/{stockId}
"""

from __future__ import annotations

from typing import Any

import httpx

from younit.exceptions import InvalidOrder
from younit.http import raise_for_status
from younit.logging import get_logger
from younit.models.portfolio import BuyingPower

_log = get_logger(__name__)


def get_buying_power(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    stock_id: int,
    market_id: int = 1,
) -> BuyingPower:
    """Fetch buying power and profile information for a stock.

    Calls ``GET /api/v1/trading/buying-power/normal/{stockId}``.

    This endpoint is step 1 of the 3-call order placement flow. The
    ``profileId`` in the response is required when placing an order.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        stock_id: Internal stock identifier.
        market_id: Market identifier (1 = EGX).

    Returns:
        Parsed :class:`~younit.models.portfolio.BuyingPower` containing
        the ``profileId`` needed for order placement.

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/v1/trading/buying-power/normal/{stock_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {"marketId": market_id}

    _log.debug("get_buying_power", url=url, stock_id=stock_id, market_id=market_id)
    response = http.get(url, headers=headers, params=params)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if data is None:
        raise InvalidOrder(
            f"No buying power data returned for stockId={stock_id}. "
            "The stock may not be available for trading on this profile."
        )
    return BuyingPower.model_validate(data)
