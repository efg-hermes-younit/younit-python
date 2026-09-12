"""Pydantic models for orders."""

from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from younit.enums import (
    ExecutionInstruction,
    ExecutionTerm,
    OperationType,
    OrderCategory,
    OrderExpireTerm,
    OrderVia,
    SubOrderVia,
)


class OrderRequest(BaseModel):
    """Request body for POST /api/v1/orders/normal.

    This maps exactly to the ``CreateNormalOrderRequest`` schema in the
    OpenAPI spec, using the field names expected by the API.

    Enum defaults are set to the values confirmed in the partner guides.
    """

    model_config = ConfigDict(populate_by_name=True)

    profile_id: int = Field(alias="profileID")
    stock_id: int = Field(alias="stockID")
    order_category: OrderCategory = Field(default=OrderCategory.NORMAL, alias="orderCategory")
    operation_type: OperationType = Field(alias="operationType")
    quantity: int = Field(alias="quantity", gt=0)
    price: float | None = Field(default=None, alias="price")
    order_expire_terms_id: OrderExpireTerm = Field(
        default=OrderExpireTerm.DAY, alias="orderExpireTermsID"
    )
    expire_date: datetime | None = Field(default=None, alias="expireDate")
    order_via: OrderVia = Field(default=OrderVia.API, alias="orderVia")
    is_market_price: bool = Field(alias="isMarketPrice")
    execution_instruction_id: ExecutionInstruction = Field(
        default=ExecutionInstruction.DEFAULT, alias="executionInstructionId"
    )
    is_edit: bool = Field(default=False, alias="isEdit")
    is_ipo: bool | None = Field(default=None, alias="isIPO")
    ipo_info_id: int | None = Field(default=None, alias="ipoInfoID")

    def to_api_dict(self) -> dict[str, object]:
        """Serialise to the camelCase dict expected by the API."""
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        # Ensure enum values are serialised as integers
        for key in (
            "orderCategory",
            "operationType",
            "orderExpireTermsID",
            "orderVia",
            "executionInstructionId",
        ):
            if key in data and hasattr(data[key], "value"):
                data[key] = int(data[key])
        if self.is_market_price:
            # Confirmed by backend team + live test: market orders must omit
            # these two fields entirely from the serialized body. Limit orders
            # are unaffected — they keep executionInstructionId/isEdit as before.
            data.pop("executionInstructionId", None)
            data.pop("isEdit", None)
        return data


class FundOrderRequest(BaseModel):
    """Request body for POST /api/v1/orders/fund.

    Maps to the ``CreateFundOrderRequest`` schema in the OpenAPI spec — a
    separate schema from ``CreateNormalOrderRequest`` used for stocks. Notably
    it has no ``isMarketPrice`` field: funds have no market/limit distinction,
    so ``price`` is treated as required here.

    Confirmed via a live-tested backend example (2026-09-02, order 54262884):
    the minimal working body is exactly ``{profileId, fundId, operationType,
    quantity, price, isIPOFund}`` — ``executionTerm``, ``orderExpireTermsID``,
    ``orderVia``, and ``subOrderVia`` are NOT part of that confirmed shape.
    Those four fields are kept as optional model fields for backward
    compatibility but default to ``None`` so ``to_api_dict()`` omits them
    unless a caller explicitly sets one.
    """

    model_config = ConfigDict(populate_by_name=True)

    profile_id: int = Field(alias="profileId")
    fund_id: int = Field(alias="fundId")
    operation_type: OperationType = Field(alias="operationType")
    quantity: int = Field(alias="quantity", gt=0)
    price: float = Field(alias="price")
    is_ipo_fund: bool = Field(default=False, alias="isIPOFund")
    # UNCONFIRMED extras absent from the confirmed minimal body — kept for
    # backward compatibility, defaulted to None so exclude_none omits them.
    execution_term: ExecutionTerm | None = Field(default=None, alias="executionTerm")
    order_expire_terms_id: OrderExpireTerm | None = Field(
        default=None, alias="orderExpireTermsID"
    )
    order_via: OrderVia | None = Field(default=None, alias="orderVia")
    sub_order_via: SubOrderVia | None = Field(default=None, alias="subOrderVia")

    def to_api_dict(self) -> dict[str, object]:
        """Serialise to the camelCase dict expected by the API."""
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        # Ensure enum values are serialised as integers
        for key in (
            "operationType",
            "executionTerm",
            "orderExpireTermsID",
            "orderVia",
            "subOrderVia",
        ):
            if key in data and hasattr(data[key], "value"):
                data[key] = int(data[key])
        return data


class FundOrderUpdateRequest(BaseModel):
    """Request body for PATCH /api/v1/orders/fund/{orderId}.

    Maps to ``UpdateFundOrderRequest`` — simpler than the stock amend body
    (``UpdateOrderRequest``): no ``profileId`` is required here.
    """

    model_config = ConfigDict(populate_by_name=True)

    quantity: int | None = Field(default=None, alias="quantity")
    price: float | None = Field(default=None, alias="price")

    def to_api_dict(self) -> dict[str, object]:
        """Serialise to the camelCase dict expected by the API."""
        return self.model_dump(by_alias=True, exclude_none=True)


class CancelOrderRequest(BaseModel):
    """Request body for POST /api/v1/orders/normal/{orderId}/cancel."""

    model_config = ConfigDict(populate_by_name=True)

    profile_id: int = Field(alias="profileId")

    def to_api_dict(self) -> dict[str, object]:
        """Serialise to the camelCase dict expected by the API."""
        return self.model_dump(by_alias=True)


class UpdateOrderRequest(BaseModel):
    """Request body for PATCH /api/v1/orders/normal/{orderId}."""

    model_config = ConfigDict(populate_by_name=True)

    profile_id: int = Field(alias="profileId")
    quantity: int | None = Field(default=None, alias="quantity")
    price: float | None = Field(default=None, alias="price")

    def to_api_dict(self) -> dict[str, object]:
        """Serialise to the camelCase dict expected by the API."""
        return self.model_dump(by_alias=True, exclude_none=True)


class Order(BaseModel):
    """An order as returned by GET /api/v1/orders/{orderId}/info.

    The API returns orders in a generic ``ObjectResult`` wrapper with
    an untyped ``data`` field (no fixed schema — confirmed against a live
    response). The live payload uses lower-camelCase keys, e.g.::

        {"orderID": 53839403, "securityID": 536, "clientID": 10208238,
         "quantity": 1, "price": 125.5, "expireDate": "...",
         "executionTermID": 8, "orderTypeID": 1, "orderAmount": 0,
         "commissionValue": 0}

    Note this response has **no order status field** — the top-level
    ``status`` in the ``ObjectResult`` wrapper is the request's own
    ``ResultStatus``, not the order's lifecycle status. Use the ActiveOrders
    stream for live status instead.

    Both the live lower-camelCase keys and the OpenAPI-style PascalCase keys
    are accepted, since the shape has been observed to vary.

    This model is intentionally reused for both stock and fund order
    results — there is no separate ``FundOrder`` model. This is an accepted
    design decision, not an oversight. For fund orders (``place_fund_order``/
    ``buy_fund``/``sell_fund`` in ``Client``), ``stock_id`` is left ``None``
    and ``fund_id`` is populated instead, as its own separate field.

    Attributes:
        order_id: The numeric order identifier.
        stock_id: Internal stock identifier. None for fund order results.
        fund_id: Internal fund identifier. None for stock order results.
        market_id: Market identifier (1 = EGX).
        profile_id: The trading profile this order belongs to.
        client_id: The account/client identifier that owns the order.
        operation_type: Buy or sell.
        price: Order price in EGP (None for market orders).
        quantity: Number of shares ordered.
        filled_quantity: Number of shares filled so far.
        status: Order status code, if returned.
        is_market_price: True if this is a market order.
        expire_date: Expiry date for Good Till Date orders.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    order_id: int | None = Field(
        default=None, validation_alias=AliasChoices("orderID", "OrderID", "orderId"), alias="OrderID"
    )
    stock_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("securityID", "StockID", "stockId"),
        alias="StockID",
    )
    fund_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("fundId", "FundID"),
        alias="FundID",
    )
    market_id: int | None = Field(default=None, alias="MarketID")
    profile_id: int | None = Field(default=None, alias="ProfileID")
    client_id: int | None = Field(
        default=None, validation_alias=AliasChoices("clientID", "ClientID"), alias="ClientID"
    )
    operation_type: str | None = Field(default=None, alias="OperationType")
    price: float | None = Field(
        default=None, validation_alias=AliasChoices("price", "Price"), alias="Price"
    )
    quantity: int | None = Field(
        default=None, validation_alias=AliasChoices("quantity", "Quantity"), alias="Quantity"
    )
    filled_quantity: int | None = Field(default=None, alias="FilledQuantity")
    status: int | None = Field(default=None, alias="Status")
    is_market_price: bool | None = Field(default=None, alias="IsMarketPrice")
    expire_date: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("expireDate", "ExpiryDate"),
        alias="ExpiryDate",
    )
    symbol: str | None = Field(default=None, alias="Symbol")


class OrderHistoryEntry(BaseModel):
    """A single row from GET /api/stocks/order-history/{MarketId}/{ProfileId}.

    Maps to the ``StocksOrderHistoryResultDto`` schema in the OpenAPI spec.
    Unlike :class:`Order`, this response is fully documented, so field names
    are mapped directly with no alias-guessing needed.
    """

    model_config = ConfigDict(populate_by_name=True)

    stock_id: int | None = Field(default=None, alias="stockId")
    order_id: int | None = Field(default=None, alias="orderId")
    order_type_id: int | None = Field(default=None, alias="orderTypeId")
    quantity: int | None = Field(default=None, alias="quantity")
    price: float | None = Field(default=None, alias="price")
    average: float | None = Field(default=None, alias="average")
    order_amount: float | None = Field(default=None, alias="orderAmount")
    stock_name: str | None = Field(default=None, alias="stockName")
    short_name: str | None = Field(default=None, alias="shortName")
    order_type: str | None = Field(default=None, alias="orderType")
    transaction_type: str | None = Field(default=None, alias="transactionType")
    placed_by: str | None = Field(default=None, alias="placedBy")
    reuter_id: str | None = Field(default=None, alias="reuterID")
    currency_short_name: str | None = Field(default=None, alias="currencyShortName")
    status: str | None = Field(default=None, alias="status")
    status_color: str | None = Field(default=None, alias="statusColor")
    reject_reason: str | None = Field(default=None, alias="rejectReason")
    order_date: datetime | None = Field(default=None, alias="orderDate")
    is_rejected: bool | None = Field(default=None, alias="isRejected")
    is_market_price: bool | None = Field(default=None, alias="isMarketPrice")
    show_price: bool | None = Field(default=None, alias="showPrice")

