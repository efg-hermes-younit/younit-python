"""Enum definitions for the Younit Trading API.

Integer enums are used to match the API's integer representation exactly.
Values documented in the partner integration guides are marked as confirmed.
Values not yet confirmed by the backend team are marked UNCONFIRMED — see
each enum class's docstring for what is blocking confirmation.

References:
- Making Your First Trade guide (canonical, overrides OpenAPI spec)
- OpenAPI spec: efg-one-trading-api.json (exhaustive enum value lists)
"""

from __future__ import annotations

from enum import Enum, IntEnum


class OrderCategory(IntEnum):
    """Order category types (_OrderCategories in OpenAPI spec).

    Confirmed against the backend's _OrderCategoryID dropdown master data:
    0 = Normal, 1 = Concealed. The partner guide's example payload uses
    ``orderCategory: 1``, but that is the guide's error — 1 is Concealed,
    not Normal, which silently placed hidden/iceberg orders and explains
    why the standard order-status flows never surfaced them.

    DEFERRED: values 2-10 are UNCONFIRMED — not documented in the OpenAPI
    spec or partner guides. Blocked on backend team confirmation.
    """

    NORMAL = 0  # Confirmed: standard limit / market order (_OrderCategoryID dropdown)
    CONCEALED = 1  # Confirmed: concealed/iceberg order (_OrderCategoryID dropdown)
    UNKNOWN_2 = 2  # unconfirmed
    UNKNOWN_3 = 3  # unconfirmed
    UNKNOWN_4 = 4  # unconfirmed
    UNKNOWN_5 = 5  # unconfirmed
    UNKNOWN_6 = 6  # unconfirmed
    UNKNOWN_7 = 7  # unconfirmed
    UNKNOWN_8 = 8  # unconfirmed
    UNKNOWN_9 = 9  # unconfirmed
    UNKNOWN_10 = 10  # unconfirmed


class OperationType(IntEnum):
    """Order operation type (buy or sell).

    Confirmed values from the partner integration guides. SELL_SAME_DAY and
    SELL_T1 are settlement-timing-specific sell variants, confirmed directly
    by the backend team on 2026-09-02: SELL_SAME_DAY closes a position
    bought the same day, and SELL_T1 closes a position settled at T+1.
    202 is unconfirmed (not documented, not assumed) and is intentionally
    omitted here.

    Automatic detection of which variant applies (e.g. based on a
    position's purchase date) isn't implemented yet, since the API doesn't
    currently expose a position's purchase/settlement date to determine
    this automatically — the caller must specify which variant applies.
    """

    BUY = 100  # Confirmed: buy order
    SELL = 200  # Confirmed: normal/standard sell
    SELL_SAME_DAY = 201  # Confirmed: same-day buy+sell close
    SELL_T1 = 203  # Confirmed: T+1 settlement sell


class OrderExpireTerm(IntEnum):
    """Order expiry terms (_OrderExpireTerms in OpenAPI spec).

    Only DAY (7) and GOOD_TILL_DATE (8) are documented in the guides.

    DEFERRED: all other values are UNCONFIRMED. Blocked on backend team
    confirmation.
    """

    UNKNOWN_0 = 0  # unconfirmed
    UNKNOWN_1 = 1  # unconfirmed
    # Required for market orders (is_market_price=True), confirmed by backend
    # team — distinct from DAY(7) used for limit orders.
    UNKNOWN_2 = 2
    UNKNOWN_3 = 3  # unconfirmed
    UNKNOWN_4 = 4  # unconfirmed
    UNKNOWN_5 = 5  # unconfirmed
    UNKNOWN_6 = 6  # unconfirmed
    DAY = 7  # Confirmed: Day order (expires at market close)
    GOOD_TILL_DATE = 8  # Confirmed: Good Till Date (expires on expireDate)
    UNKNOWN_9 = 9  # unconfirmed
    UNKNOWN_10 = 10  # unconfirmed
    UNKNOWN_11 = 11  # unconfirmed


class OrderVia(IntEnum):
    """Order submission channel (_Ordervia in OpenAPI spec).

    Only value 8 is documented in the partner integration guides.
    All other values appear in the OpenAPI spec but are not documented.

    DEFERRED: all other values are UNCONFIRMED. Blocked on backend team
    confirmation.
    """

    UNKNOWN_0 = 0  # unconfirmed
    UNKNOWN_1 = 1  # unconfirmed
    UNKNOWN_2 = 2  # unconfirmed
    UNKNOWN_3 = 3  # unconfirmed
    UNKNOWN_4 = 4  # unconfirmed
    UNKNOWN_5 = 5  # unconfirmed
    UNKNOWN_6 = 6  # unconfirmed
    UNKNOWN_7 = 7  # unconfirmed
    API = 8  # Confirmed: API/programmatic order submission
    UNKNOWN_9 = 9  # unconfirmed
    UNKNOWN_10 = 10  # unconfirmed
    UNKNOWN_11 = 11  # unconfirmed
    UNKNOWN_12 = 12  # unconfirmed
    UNKNOWN_14 = 14  # unconfirmed (note: 13 absent in spec)
    UNKNOWN_15 = 15  # unconfirmed
    UNKNOWN_16 = 16  # unconfirmed
    UNKNOWN_17 = 17  # unconfirmed
    UNKNOWN_18 = 18  # unconfirmed
    UNKNOWN_19 = 19  # unconfirmed
    UNKNOWN_20 = 20  # unconfirmed


class SubOrderVia(IntEnum):
    """Sub-order submission channel (_SubOrderVia in OpenAPI spec).

    No values are documented in the partner integration guides.
    All values are from the OpenAPI spec only.

    DEFERRED: all values are UNCONFIRMED. Blocked on backend team confirmation.
    """

    UNKNOWN_0 = 0
    UNKNOWN_1 = 1
    UNKNOWN_2 = 2
    UNKNOWN_3 = 3
    UNKNOWN_4 = 4
    UNKNOWN_5 = 5
    UNKNOWN_6 = 6
    UNKNOWN_7 = 7
    UNKNOWN_8 = 8
    UNKNOWN_9 = 9
    UNKNOWN_10 = 10
    UNKNOWN_11 = 11
    UNKNOWN_12 = 12
    UNKNOWN_13 = 13
    UNKNOWN_14 = 14
    UNKNOWN_15 = 15
    UNKNOWN_16 = 16
    UNKNOWN_17 = 17
    UNKNOWN_18 = 18
    UNKNOWN_19 = 19
    UNKNOWN_20 = 20
    UNKNOWN_21 = 21
    UNKNOWN_22 = 22
    UNKNOWN_23 = 23
    UNKNOWN_24 = 24


class ExecutionInstruction(IntEnum):
    """Execution instruction (_ExecutionInstructions in OpenAPI spec).

    Only value 1 is documented in the partner integration guides.
    """

    DEFAULT = 1  # Confirmed: default execution instruction


class ExecutionTerm(IntEnum):
    """Execution terms (_ExecutionTerms in OpenAPI spec).

    No values are explicitly documented in the partner integration guides.
    Values from the OpenAPI spec only.

    DEFERRED: all values are UNCONFIRMED. Blocked on backend team confirmation.
    """

    UNKNOWN_0 = 0
    UNKNOWN_1 = 1
    UNKNOWN_2 = 2
    UNKNOWN_3 = 3
    UNKNOWN_4 = 4
    UNKNOWN_5 = 5
    UNKNOWN_6 = 6
    UNKNOWN_7 = 7
    UNKNOWN_8 = 8
    UNKNOWN_9 = 9
    UNKNOWN_10 = 10


class OrderStatus(IntEnum):
    """Order status values returned in order info responses.

    DEFERRED: this enum does not appear in the OpenAPI spec. These values are
    inferred from typical broker API patterns and may not be accurate. Do not
    rely on specific numeric values until the complete mapping is confirmed
    with the backend team.
    """

    PENDING = 1  # unconfirmed
    ACTIVE = 2  # unconfirmed
    EXECUTED = 3  # unconfirmed
    CANCELLED = 4  # unconfirmed
    REJECTED = 5  # unconfirmed
    PARTIAL = 6  # unconfirmed
    EXPIRED = 7  # unconfirmed


class ChartPeriod(str, Enum):  # noqa: UP042
    """Chart period for historical price data feed.

    Used with :meth:`~younit.client.Client.historical_prices`.
    Values match the ``Period`` query parameter of
    ``GET /api/charts/GetChartingHistoricalDataFeed``.
    """

    DAY = "Day"
    WEEK = "Week"
    MONTH = "Month"
    YEAR = "Year"
