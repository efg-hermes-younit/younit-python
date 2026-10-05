"""Order management endpoints.

Endpoints:
- POST /api/v1/orders/normal           — place a normal (stock) order
- POST /api/v1/orders/normal/{orderId}/cancel  — cancel an order
- PATCH /api/v1/orders/normal/{orderId}        — amend an order
- GET /api/v1/orders/{orderId}/info    — get order status
- POST /api/v1/orders/fund             — place a fund order
- PATCH /api/v1/orders/fund/{orderId}          — amend a fund order
- POST /api/v1/orders/fund/{orderId}/cancel    — cancel a fund order

IMPORTANT: POST /api/v1/orders/normal and POST /api/v1/orders/fund are NEVER
retried. A timeout on either endpoint must surface to the caller. The user
must then call list_orders or get_order to determine whether the order
landed.
"""

from __future__ import annotations

from typing import Any

import httpx

from younit.exceptions import APIError, OrderRejected
from younit.http import raise_for_status
from younit.logging import get_logger
from younit.models.orders import (
    CancelOrderRequest,
    FundOrderRequest,
    FundOrderUpdateRequest,
    Order,
    OrderHistoryEntry,
    OrderRequest,
    UpdateOrderRequest,
)

_log = get_logger(__name__)


def place_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    request: OrderRequest,
) -> int:
    """Place a normal order on the exchange.

    Calls ``POST /api/v1/orders/normal``.

    CRITICAL: This request is NEVER retried. If this call times out, the
    caller MUST call get_order or list_orders to verify whether the order
    was received by the exchange.

    Following a backend change request, the ``data`` field of the response
    envelope is now an object carrying the real order ID directly (confirmed
    live 2026-09-02)::

        {"messages": [""], "status": 1, "data": {"result": true, "orderId": 54250949}}

    This replaced the older shape where ``data`` was a bare boolean with no
    order ID (``{"messages": [...], "status": 1, "data": true}``).

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        request: Fully populated :class:`~younit.models.orders.OrderRequest`.

    Returns:
        The real numeric order ID assigned by the exchange.

    Raises:
        OrderRejected: If the API returns a failure response.
        APIError: On HTTP error responses, or if a successful response is
            missing the expected ``orderId``.
        httpx.TimeoutException: On timeout — surfaces directly to the caller.
    """
    url = f"{base_url}/api/v1/orders/normal"
    headers = {
        **default_headers,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = request.to_api_dict()

    _log.info(
        "placing_order",
        stock_id=request.stock_id,
        operation_type=int(request.operation_type),
        quantity=request.quantity,
        is_market_price=request.is_market_price,
        # price intentionally not logged at default level to avoid filling logs
    )

    # NOTE: No retry wrapper here — this is intentional per non-negotiables.
    response = http.post(url, headers=headers, json=body)
    raise_for_status(response)

    data: Any = response.json()
    messages = (data.get("messages") or []) if isinstance(data, dict) else []
    inner = data.get("data") if isinstance(data, dict) else None

    order_id: Any = None
    success = True
    if isinstance(inner, dict):
        # New shape: data.result indicates success/failure, data.orderId is
        # the real order ID.
        success = bool(inner.get("result"))
        order_id = inner.get("orderId")
    elif inner is False:
        # Legacy BooleanResult shape (pre change-request): data was a bare
        # bool with no order ID. Kept only as a defensive fallback.
        success = False

    if not success:
        raise OrderRejected(
            "; ".join(str(m) for m in messages if m) or "Order was rejected by the exchange."
        )
    if order_id is None:
        raise APIError(
            "Order placement succeeded but the response did not include an orderId.",
            status_code=response.status_code,
            response_body=response.text,
        )

    _log.info("order_placed_successfully", stock_id=request.stock_id, order_id=order_id)
    return int(order_id)


def cancel_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    order_id: int,
    profile_id: int,
) -> bool:
    """Cancel an existing order.

    Calls ``POST /api/v1/orders/normal/{orderId}/cancel``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        order_id: The numeric order identifier to cancel.
        profile_id: The trading profile ID that owns this order.

    Returns:
        True if the cancellation was accepted.

    Raises:
        OrderRejected: If the cancellation is rejected.
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/v1/orders/normal/{order_id}/cancel"
    headers = {
        **default_headers,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request = CancelOrderRequest(profile_id=profile_id)

    _log.info("cancelling_order", order_id=order_id, profile_id=profile_id)
    response = http.post(url, headers=headers, json=request.to_api_dict())
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict):
        success = data.get("data")
        messages = data.get("messages") or []
        if success is False:
            raise OrderRejected(
                "; ".join(str(m) for m in messages) or "Order cancellation was rejected."
            )

    _log.info("order_cancelled_successfully", order_id=order_id)
    return True


def amend_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    order_id: int,
    profile_id: int,
    quantity: int | None = None,
    price: float | None = None,
) -> bool:
    """Amend an existing order (change quantity and/or price).

    Calls ``PATCH /api/v1/orders/normal/{orderId}``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        order_id: The numeric order identifier to amend.
        profile_id: The trading profile ID that owns this order.
        quantity: New quantity (shares). If None, keeps current quantity.
        price: New limit price in EGP. If None, keeps current price.

    Returns:
        True if the amendment was accepted.

    Raises:
        OrderRejected: If the amendment is rejected.
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/v1/orders/normal/{order_id}"
    headers = {
        **default_headers,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request = UpdateOrderRequest(
        profile_id=profile_id,
        quantity=quantity,
        price=price,
    )

    _log.info("amending_order", order_id=order_id, profile_id=profile_id)
    response = http.patch(url, headers=headers, json=request.to_api_dict())
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict):
        success = data.get("data")
        messages = data.get("messages") or []
        if success is False:
            raise OrderRejected(
                "; ".join(str(m) for m in messages) or "Order amendment was rejected."
            )

    _log.info("order_amended_successfully", order_id=order_id)
    return True


def place_fund_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    request: FundOrderRequest,
) -> int:
    """Place a fund order on the exchange.

    Calls ``POST /api/v1/orders/fund``.

    CRITICAL: This request is NEVER retried. If this call times out, the
    caller MUST verify separately whether the order was received by the
    exchange.

    Confirmed live 2026-09-02 (order 54262884): the response envelope matches
    the stock order shape exactly — ``data`` is an object carrying the real
    order ID directly::

        {"data": {"orderId": 54262884, "result": true}, "status": 1}

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        request: Fully populated :class:`~younit.models.orders.FundOrderRequest`.

    Returns:
        The real numeric order ID assigned by the exchange.

    Raises:
        OrderRejected: If the API returns a failure response.
        APIError: On HTTP error responses, or if a successful response is
            missing the expected ``orderId``.
        httpx.TimeoutException: On timeout — surfaces directly to the caller.
    """
    url = f"{base_url}/api/v1/orders/fund"
    headers = {
        **default_headers,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = request.to_api_dict()

    _log.info(
        "placing_fund_order",
        fund_id=request.fund_id,
        operation_type=int(request.operation_type),
        quantity=request.quantity,
        # price intentionally not logged at default level to avoid filling logs
    )

    # NOTE: No retry wrapper here — intentional, mirroring place_order.
    response = http.post(url, headers=headers, json=body)
    raise_for_status(response)

    data: Any = response.json()
    messages = (data.get("messages") or []) if isinstance(data, dict) else []
    inner = data.get("data") if isinstance(data, dict) else None

    order_id: Any = None
    success = True
    if isinstance(inner, dict):
        # Matches place_order's shape: data.result indicates success/failure,
        # data.orderId is the real order ID.
        success = bool(inner.get("result"))
        order_id = inner.get("orderId")
    elif inner is False:
        # Legacy bare-bool BooleanResult shape, kept as a defensive fallback.
        success = False

    if not success:
        raise OrderRejected(
            "; ".join(str(m) for m in messages if m) or "Fund order was rejected by the exchange."
        )
    if order_id is None:
        raise APIError(
            "Fund order placement succeeded but the response did not include an orderId.",
            status_code=response.status_code,
            response_body=response.text,
        )

    _log.info("fund_order_placed_successfully", fund_id=request.fund_id, order_id=order_id)
    return int(order_id)


def amend_fund_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    order_id: int,
    quantity: int | None = None,
    price: float | None = None,
) -> bool:
    """Amend an existing fund order (change quantity and/or price).

    Calls ``PATCH /api/v1/orders/fund/{orderId}``. Unlike the stock amend
    body, no ``profileId`` is required here (per ``UpdateFundOrderRequest``).

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        order_id: The numeric fund order identifier to amend.
        quantity: New quantity (units). If None, keeps current quantity.
        price: New price. If None, keeps current price.

    Returns:
        True if the amendment was accepted.

    Raises:
        OrderRejected: If the amendment is rejected.
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/v1/orders/fund/{order_id}"
    headers = {
        **default_headers,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request = FundOrderUpdateRequest(quantity=quantity, price=price)

    _log.info("amending_fund_order", order_id=order_id)
    response = http.patch(url, headers=headers, json=request.to_api_dict())
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict):
        success = data.get("data")
        messages = data.get("messages") or []
        if success is False:
            raise OrderRejected(
                "; ".join(str(m) for m in messages) or "Fund order amendment was rejected."
            )

    _log.info("fund_order_amended_successfully", order_id=order_id)
    return True


def cancel_fund_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    order_id: int,
) -> bool:
    """Cancel an existing fund order.

    Calls ``POST /api/v1/orders/fund/{orderId}/cancel`` — a dedicated
    fund-specific cancel endpoint confirmed in the OpenAPI spec, separate
    from the stock cancel endpoint (``/api/v1/orders/normal/{orderId}/cancel``).
    Unlike the stock cancel endpoint, this one takes no request body (no
    ``profileId`` needed, per the spec).

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        order_id: The numeric fund order identifier to cancel.

    Returns:
        True if the cancellation was accepted.

    Raises:
        OrderRejected: If the cancellation is rejected.
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/v1/orders/fund/{order_id}/cancel"
    headers = {
        **default_headers,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    _log.info("cancelling_fund_order", order_id=order_id)
    response = http.post(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict):
        success = data.get("data")
        messages = data.get("messages") or []
        if success is False:
            raise OrderRejected(
                "; ".join(str(m) for m in messages) or "Fund order cancellation was rejected."
            )

    _log.info("fund_order_cancelled_successfully", order_id=order_id)
    return True


def get_order(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    order_id: int,
) -> Order:
    """Fetch the current status of an order.

    Calls ``GET /api/v1/orders/{orderId}/info``.

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        order_id: The numeric order identifier.

    Returns:
        Parsed :class:`~younit.models.orders.Order`.

    Raises:
        NotFound: If the order does not exist.
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/v1/orders/{order_id}/info"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_order", url=url, order_id=order_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if data is None:
        return Order()
    if isinstance(data, dict):
        return Order.model_validate(data)
    return Order()


def get_order_history(
    http: httpx.Client,
    base_url: str,
    default_headers: dict[str, str],
    *,
    token: str,
    market_id: int,
    profile_id: int,
) -> list[OrderHistoryEntry]:
    """Fetch the historical (closed/rejected/filled) stock orders for a profile.

    Calls ``GET /api/stocks/order-history/{MarketId}/{ProfileId}`` — the
    only order-history endpoint documented in the OpenAPI spec (there is no
    simple list-all-orders endpoint).

    Args:
        http: httpx client instance.
        base_url: API base URL.
        default_headers: Standard headers.
        token: Current client bearer token.
        market_id: Market identifier (1 = EGX).
        profile_id: The trading profile ID to fetch history for.

    Returns:
        List of :class:`~younit.models.orders.OrderHistoryEntry`, as returned
        by the API (order not guaranteed).

    Raises:
        APIError: On HTTP error responses.
    """
    url = f"{base_url}/api/stocks/order-history/{market_id}/{profile_id}"
    headers = {**default_headers, "Authorization": f"Bearer {token}"}

    _log.debug("get_order_history", url=url, market_id=market_id, profile_id=profile_id)
    response = http.get(url, headers=headers)
    raise_for_status(response)

    data: Any = response.json()
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if not isinstance(data, list):
        return []
    return [OrderHistoryEntry.model_validate(row) for row in data if isinstance(row, dict)]
