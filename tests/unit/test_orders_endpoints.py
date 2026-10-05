"""Unit tests for the orders endpoint functions (direct, not via Client)."""

from __future__ import annotations

import httpx
import pytest
import respx

from younit.endpoints.orders import (
    amend_fund_order,
    amend_order,
    cancel_fund_order,
    cancel_order,
    get_order,
    get_order_history,
    place_fund_order,
    place_order,
)
from younit.enums import OperationType
from younit.exceptions import APIError, OrderRejected
from younit.models.orders import FundOrderRequest, OrderRequest

BASE_URL = "https://api.test"
HEADERS: dict[str, str] = {}


def _order_request(**overrides: object) -> OrderRequest:
    defaults: dict[str, object] = {
        "profile_id": 1,
        "stock_id": 101,
        "operation_type": OperationType.BUY,
        "quantity": 10,
        "is_market_price": True,
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)  # type: ignore[arg-type]


def _fund_order_request(**overrides: object) -> FundOrderRequest:
    defaults: dict[str, object] = {
        "profile_id": 1,
        "fund_id": 55,
        "operation_type": OperationType.BUY,
        "quantity": 10,
        "price": 100.0,
    }
    defaults.update(overrides)
    return FundOrderRequest(**defaults)  # type: ignore[arg-type]


class TestPlaceOrder:
    def test_legacy_bare_bool_failure_raises_order_rejected(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json={"data": False, "messages": ["rejected"]})
        )
        with httpx.Client() as http, pytest.raises(OrderRejected, match="rejected"):
            place_order(http, BASE_URL, HEADERS, token="tok", request=_order_request())

    def test_missing_order_id_raises_api_error(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json={"data": {"result": True}, "messages": []})
        )
        with httpx.Client() as http, pytest.raises(APIError, match="did not include an orderId"):
            place_order(http, BASE_URL, HEADERS, token="tok", request=_order_request())

    def test_success_returns_order_id(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": True, "orderId": 42}, "messages": []}
            )
        )
        with httpx.Client() as http:
            order_id = place_order(http, BASE_URL, HEADERS, token="tok", request=_order_request())
        assert order_id == 42


class TestPlaceFundOrder:
    def test_legacy_bare_bool_failure_raises_order_rejected(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(200, json={"data": False, "messages": ["no funds"]})
        )
        with httpx.Client() as http, pytest.raises(OrderRejected, match="no funds"):
            place_fund_order(http, BASE_URL, HEADERS, token="tok", request=_fund_order_request())

    def test_missing_order_id_raises_api_error(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(200, json={"data": {"result": True}, "messages": []})
        )
        with httpx.Client() as http, pytest.raises(APIError, match="did not include an orderId"):
            place_fund_order(http, BASE_URL, HEADERS, token="tok", request=_fund_order_request())

    def test_success_returns_order_id(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": True, "orderId": 99}, "messages": []}
            )
        )
        with httpx.Client() as http:
            order_id = place_fund_order(
                http, BASE_URL, HEADERS, token="tok", request=_fund_order_request()
            )
        assert order_id == 99


class TestCancelOrder:
    def test_rejection_raises_order_rejected(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/normal/5/cancel").mock(
            return_value=httpx.Response(200, json={"data": False, "messages": ["too late"]})
        )
        with httpx.Client() as http, pytest.raises(OrderRejected, match="too late"):
            cancel_order(http, BASE_URL, HEADERS, token="tok", order_id=5, profile_id=1)

    def test_success_returns_true(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/normal/5/cancel").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )
        with httpx.Client() as http:
            assert cancel_order(http, BASE_URL, HEADERS, token="tok", order_id=5, profile_id=1)


class TestAmendOrder:
    def test_rejection_raises_order_rejected(self, respx_mock: respx.MockRouter):
        respx_mock.patch(f"{BASE_URL}/api/v1/orders/normal/5").mock(
            return_value=httpx.Response(200, json={"data": False, "messages": ["bad price"]})
        )
        with httpx.Client() as http, pytest.raises(OrderRejected, match="bad price"):
            amend_order(http, BASE_URL, HEADERS, token="tok", order_id=5, profile_id=1, price=10.0)

    def test_success_returns_true(self, respx_mock: respx.MockRouter):
        respx_mock.patch(f"{BASE_URL}/api/v1/orders/normal/5").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )
        with httpx.Client() as http:
            assert amend_order(
                http, BASE_URL, HEADERS, token="tok", order_id=5, profile_id=1, price=10.0
            )


class TestAmendFundOrderRejection:
    def test_non_dict_response_does_not_raise(self, respx_mock: respx.MockRouter):
        respx_mock.patch(f"{BASE_URL}/api/v1/orders/fund/5").mock(
            return_value=httpx.Response(200, json=["unexpected"])
        )
        with httpx.Client() as http:
            assert amend_fund_order(http, BASE_URL, HEADERS, token="tok", order_id=5, price=10.0)


class TestCancelFundOrderRejection:
    def test_non_dict_response_does_not_raise(self, respx_mock: respx.MockRouter):
        respx_mock.post(f"{BASE_URL}/api/v1/orders/fund/5/cancel").mock(
            return_value=httpx.Response(200, json=["unexpected"])
        )
        with httpx.Client() as http:
            assert cancel_fund_order(http, BASE_URL, HEADERS, token="tok", order_id=5)


class TestGetOrder:
    def test_null_data_returns_default_order(self, respx_mock: respx.MockRouter):
        respx_mock.get(f"{BASE_URL}/api/v1/orders/5/info").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        with httpx.Client() as http:
            order = get_order(http, BASE_URL, HEADERS, token="tok", order_id=5)
        assert order.order_id is None

    def test_non_dict_data_returns_default_order(self, respx_mock: respx.MockRouter):
        respx_mock.get(f"{BASE_URL}/api/v1/orders/5/info").mock(
            return_value=httpx.Response(200, json={"data": "unexpected"})
        )
        with httpx.Client() as http:
            order = get_order(http, BASE_URL, HEADERS, token="tok", order_id=5)
        assert order.order_id is None

    def test_dict_data_is_parsed(self, respx_mock: respx.MockRouter):
        respx_mock.get(f"{BASE_URL}/api/v1/orders/5/info").mock(
            return_value=httpx.Response(200, json={"data": {"orderID": 5, "quantity": 1}})
        )
        with httpx.Client() as http:
            order = get_order(http, BASE_URL, HEADERS, token="tok", order_id=5)
        assert order.order_id == 5


class TestGetOrderHistory:
    def test_non_list_data_returns_empty(self, respx_mock: respx.MockRouter):
        respx_mock.get(f"{BASE_URL}/api/stocks/order-history/1/1").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        with httpx.Client() as http:
            history = get_order_history(
                http, BASE_URL, HEADERS, token="tok", market_id=1, profile_id=1
            )
        assert history == []

    def test_non_dict_rows_are_skipped(self, respx_mock: respx.MockRouter):
        respx_mock.get(f"{BASE_URL}/api/stocks/order-history/1/1").mock(
            return_value=httpx.Response(
                200, json={"data": ["not-a-dict", {"orderId": 1, "quantity": 2}]}
            )
        )
        with httpx.Client() as http:
            history = get_order_history(
                http, BASE_URL, HEADERS, token="tok", market_id=1, profile_id=1
            )
        assert len(history) == 1
        assert history[0].order_id == 1
