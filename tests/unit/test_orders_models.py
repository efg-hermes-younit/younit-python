"""Unit tests for younit.models.orders."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from younit.enums import (
    ExecutionInstruction,
    ExecutionTerm,
    OperationType,
    OrderExpireTerm,
    OrderVia,
    SubOrderVia,
)
from younit.models.orders import FundOrderRequest, FundOrderUpdateRequest, Order, OrderRequest


class TestOrderStubConstruction:
    """Mirrors the Order(...) stub built by Client.place_order() when confirm=False."""

    def test_snake_case_kwargs_populate_typed_fields(self) -> None:
        stub = Order(
            order_id=54250949,
            stock_id=104879,
            operation_type=OperationType.BUY.name,
            quantity=1,
            price=17.9,
            is_market_price=False,
        )

        assert stub.order_id == 54250949
        assert stub.stock_id == 104879
        assert stub.operation_type == "BUY"
        assert stub.quantity == 1
        assert stub.price == 17.9
        assert stub.is_market_price is False
        # Nothing should have spilled into extra fields (extra="allow" would
        # silently swallow mismatched kwargs instead of raising).
        assert stub.model_extra == {}

    def test_fund_order_stub_populates_fund_id_not_stock_id(self) -> None:
        # Mirrors the Order(...) stub built by Client.place_fund_order().
        stub = Order(
            order_id=54262884,
            fund_id=42,
            operation_type=OperationType.BUY.name,
            quantity=10,
            price=100.5,
        )

        assert stub.order_id == 54262884
        assert stub.fund_id == 42
        assert stub.stock_id is None
        assert stub.model_extra == {}


class TestOrderRequestToApiDict:
    def test_gtd_order_expire_date_is_json_serializable(self) -> None:
        request = OrderRequest(
            profileID=1,
            stockID=536,
            operationType=OperationType.BUY,
            quantity=100,
            price=82.5,
            orderExpireTermsID=OrderExpireTerm.GOOD_TILL_DATE,
            expireDate=datetime(2026, 9, 1, 0, 0, 0),
            isMarketPrice=False,
        )

        data = request.to_api_dict()

        # Must round-trip through json.dumps() without raising.
        json.dumps(data)

        assert isinstance(data["expireDate"], str)

    def test_market_order_uses_confirmed_values_and_omits_fields(self) -> None:
        """Confirmed via backend team + live test (see enums.OrderExpireTerm.UNKNOWN_2)."""
        request = OrderRequest(
            profileID=1,
            stockID=536,
            operationType=OperationType.BUY,
            quantity=10,
            price=0.0,
            orderExpireTermsID=OrderExpireTerm.UNKNOWN_2,
            isMarketPrice=True,
        )

        data = request.to_api_dict()

        assert data["price"] == 0
        assert data["orderExpireTermsID"] == 2
        assert "executionInstructionId" not in data
        assert "isEdit" not in data

    def test_limit_order_keeps_execution_instruction_and_is_edit(self) -> None:
        """Limit orders must be completely unaffected by the market-order fix."""
        request = OrderRequest(
            profileID=1,
            stockID=536,
            operationType=OperationType.BUY,
            quantity=10,
            price=82.5,
            isMarketPrice=False,
        )

        data = request.to_api_dict()

        assert data["price"] == 82.5
        assert data["orderExpireTermsID"] == int(OrderExpireTerm.DAY)
        assert data["executionInstructionId"] == int(ExecutionInstruction.DEFAULT)
        assert data["isEdit"] is False


class TestFundOrderRequestToApiDict:
    def test_required_fields_and_defaults_serialise_to_camel_case(self) -> None:
        request = FundOrderRequest(
            profileId=1,
            fundId=42,
            operationType=OperationType.BUY,
            quantity=10,
            price=100.5,
        )

        data = request.to_api_dict()
        json.dumps(data)  # must be JSON-serializable

        assert data["profileId"] == 1
        assert data["fundId"] == 42
        assert data["operationType"] == int(OperationType.BUY)
        assert data["quantity"] == 10
        assert data["price"] == 100.5
        assert data["isIPOFund"] is False

    def test_matches_confirmed_minimal_shape_only(self) -> None:
        # Confirmed via live-tested backend example (2026-09-02, order
        # 54262884): the working body has exactly these 6 keys, nothing more.
        request = FundOrderRequest(
            profileId=1,
            fundId=42,
            operationType=OperationType.BUY,
            quantity=10,
            price=100.5,
        )

        data = request.to_api_dict()

        assert set(data.keys()) == {
            "profileId",
            "fundId",
            "operationType",
            "quantity",
            "price",
            "isIPOFund",
        }
        assert "executionTerm" not in data
        assert "orderExpireTermsID" not in data
        assert "orderVia" not in data
        assert "subOrderVia" not in data

    def test_price_is_required(self) -> None:
        with pytest.raises(ValidationError):
            FundOrderRequest(
                profileId=1,
                fundId=42,
                operationType=OperationType.BUY,
                quantity=10,
            )

    def test_execution_term_and_sub_order_via_included_when_set(self) -> None:
        request = FundOrderRequest(
            profileId=1,
            fundId=42,
            operationType=OperationType.SELL,
            quantity=5,
            price=10.0,
            executionTerm=ExecutionTerm.UNKNOWN_1,
            orderExpireTermsID=OrderExpireTerm.GOOD_TILL_DATE,
            orderVia=OrderVia.API,
            subOrderVia=SubOrderVia.UNKNOWN_2,
        )

        data = request.to_api_dict()

        assert data["executionTerm"] == int(ExecutionTerm.UNKNOWN_1)
        assert data["orderExpireTermsID"] == int(OrderExpireTerm.GOOD_TILL_DATE)
        assert data["orderVia"] == int(OrderVia.API)
        assert data["subOrderVia"] == int(SubOrderVia.UNKNOWN_2)


class TestFundOrderUpdateRequestToApiDict:
    def test_only_quantity_and_price_present_no_profile_id(self) -> None:
        request = FundOrderUpdateRequest(quantity=20, price=12.5)

        data = request.to_api_dict()

        assert data == {"quantity": 20, "price": 12.5}
        assert "profileId" not in data

    def test_omitted_fields_excluded(self) -> None:
        request = FundOrderUpdateRequest(price=15.0)

        data = request.to_api_dict()

        assert data == {"price": 15.0}

