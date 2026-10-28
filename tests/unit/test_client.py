"""Unit tests for Client market-data methods."""

from __future__ import annotations

import inspect
import json
import time
from datetime import datetime
from typing import ClassVar
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import conftest as conf
import httpx
import pytest

import younit.client as client_module
from younit.auth import _TokenRecord
from younit.client import Client
from younit.enums import OperationType, OrderExpireTerm
from younit.exceptions import APIError, AuthError, InvalidOrder, OrderRejected, Unauthorized
from younit.models.market_data import StockInfo
from younit.models.orders import Order
from younit.models.streaming import MarketUpdate, Subscription, SymbolUpdate

FAKE_BASE_URL = conf.FAKE_BASE_URL

RAW_STOCKS = [
    {
        "stockId": 101,
        "symbol": "COMI",
        "stockName": "Commercial International Bank",
        "reuterCode": "COMI.CA",
        "marketId": 1,
        "price": 65.5,
        "changePercent": 1.2,
        "volume": 1000,
        "isIntraday": True,
        "isTPlus1": False,
    }
]

# Captured live 2026-08-30 from GET /api/portfolio/GetStocksPortfolio?MarketId=1
# (trimmed to the fields Position actually consumes).
RAW_POSITIONS_RESPONSE = {
    "messages": None,
    "data": {
        "currency": "EGP",
        "stocks": [
            {
                "securityID": 294,
                "ReuterID": "EAST.CA",
                "quantity": 1,
                "unSettledQty": 1,
                "quantiyValidForSale": 0,
                "frozenQty": 0,
                "averageCost": 38.269,
                "shortNameE": "Eastern Company",
                "shortNameA": (
                    "\u0627\u0644\u0634\u0631\u0642\u064a\u0629 "
                    "\u0644\u0644\u062f\u062e\u0627\u0646"
                ),
                "marketPrice": 35.07,
                "realizedProfit": 0,
                "unRealizedProfit": -3.199,
                "unRealizedProfitPercentage": -8.3592463874154,
                "profitOrLoss": 0,
                "totalValue": 38.269,
                "holdingValue": 35.07,
                "isFund": False,
                "isSuspended": False,
                "currencyShortName": "EGP",
            },
            {
                "securityID": 319,
                "ReuterID": "ABUK.CA",
                "quantity": 1,
                "unSettledQty": 1,
                "quantiyValidForSale": 0,
                "frozenQty": 0,
                "averageCost": 82.167,
                "shortNameE": "AboKir Fertilize",
                "shortNameA": (
                    "\u0627\u0628\u0648\u0642\u064a\u0631 "
                    "\u0644\u0644\u0627\u0633\u0645\u062f\u0629"
                ),
                "marketPrice": 79.4,
                "realizedProfit": 0,
                "unRealizedProfit": -2.767,
                "unRealizedProfitPercentage": -3.3675319775579,
                "profitOrLoss": 0,
                "totalValue": 82.167,
                "holdingValue": 79.4,
                "isFund": False,
                "isSuspended": False,
                "currencyShortName": "EGP",
            },
            {
                "securityID": 536,
                "ReuterID": "COMI.CA",
                "quantity": 1,
                "unSettledQty": 1,
                "quantiyValidForSale": 0,
                "frozenQty": 0,
                "averageCost": 141.753,
                "shortNameE": "Commercial Bank",
                "shortNameA": (
                    "\u0627\u0644\u0628\u0646\u0643 \u0627\u0644\u062a\u062c\u0627\u0631\u064a "
                    "\u0627\u0644\u062f\u0648\u0644\u064a"
                ),
                "marketPrice": 138.1,
                "realizedProfit": 0,
                "unRealizedProfit": -3.653,
                "unRealizedProfitPercentage": -2.577017770347,
                "profitOrLoss": 0,
                "totalValue": 141.753,
                "holdingValue": 138.1,
                "isFund": False,
                "isSuspended": False,
                "currencyShortName": "EGP",
            },
            {
                "securityID": 104879,
                "ReuterID": "FWRY.CA",
                "quantity": 1,
                "unSettledQty": 1,
                "quantiyValidForSale": 0,
                "frozenQty": 0,
                "averageCost": 21.831,
                "shortNameE": "Fawry for Banks Tec",
                "shortNameA": (
                    "\u0641\u0648\u0631\u064a \u0644\u062a\u0643\u0646\u0648\u0644\u0648\u062c"
                    "\u064a\u0627 \u0627\u0644\u0628\u0646\u0648\u0643"
                ),
                "marketPrice": 18.99,
                "realizedProfit": 0,
                "unRealizedProfit": -2.841,
                "unRealizedProfitPercentage": -13.013604507352,
                "profitOrLoss": 0,
                "totalValue": 21.831,
                "holdingValue": 18.99,
                "isFund": False,
                "isSuspended": False,
                "currencyShortName": "EGP",
            },
        ],
        "stocksValue": 197.53,
    },
}

# Captured live 2026-09-04 from GET /api/portfolio/GetPortfolioSecurities?marketId=1
# (trimmed to 1 stock row; no real fund row has ever been observed live yet —
# the fund row below is synthetic, built to match DetailedSecurityPositionRow's
# confirmed schema/casing exactly).
RAW_PORTFOLIO_SECURITIES_RESPONSE = {
    "messages": None,
    "data": {
        "securityPositions": [
            {
                "securityID": 319,
                "reuterID": "ABUK.CA",
                "quantity": 1,
                "unSettledQty": 0,
                "quantiyValidForSale": 1,
                "frozenQty": 0,
                "averageCost": 82.167,
                "shortNameE": "AboKir Fertilize",
                "shortNameA": (
                    "\u0627\u0628\u0648\u0642\u064a\u0631 "
                    "\u0644\u0644\u0627\u0633\u0645\u062f\u0629"
                ),
                "marketPrice": 92.39,
                "realizedProfit": 0,
                "unRealizedProfit": 10.223,
                "unRealizedProfitPercentage": 12.44173451629,
                "profitOrLoss": 0,
                "totalValue": 82.167,
                "isFund": False,
                "holdingValue": 92.39,
                "fundType": None,
                "showUnsettledQty": False,
                "showFrozenQty": False,
                "isSuspended": False,
                "isInvest": False,
                "isRedeem": False,
                "currencyShortName": "EGP",
            },
            {
                "securityID": 9001,
                "reuterID": "SIGP.CA",
                "quantity": 10,
                "unSettledQty": 10,
                "quantiyValidForSale": 0,
                "frozenQty": 0,
                "averageCost": 100.0,
                "shortNameE": "Some Income Fund",
                "shortNameA": "\u0635\u0646\u062f\u0648\u0642 \u062f\u062e\u0644",
                "marketPrice": 101.5,
                "realizedProfit": 0,
                "unRealizedProfit": 15.0,
                "unRealizedProfitPercentage": 1.5,
                "profitOrLoss": 0,
                "totalValue": 1000.0,
                "isFund": True,
                "holdingValue": 1015.0,
                "fundType": "Money Market",
                "showUnsettledQty": True,
                "showFrozenQty": False,
                "isSuspended": False,
                "isInvest": True,
                "isRedeem": False,
                "currencyShortName": "EGP",
            },
        ],
        "stocks": {
            "unRealizedProfit": 10.223,
            "investmentValue": 82.167,
            "unRealizedProfitPercentage": 12.44,
        },
        "funds": {
            "unRealizedProfit": 15.0,
            "investmentValue": 1000.0,
            "unRealizedProfitPercentage": 1.5,
        },
    },
}


def _make_client(respx_mock, raw_stocks=RAW_STOCKS) -> Client:
    respx_mock.post(conf.TOKEN_URL).mock(
        return_value=httpx.Response(200, json=conf.CLIENT_TOKEN_RESPONSE)
    )
    respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/market/1", name="market_stocks").mock(
        return_value=httpx.Response(200, json=raw_stocks)
    )
    return Client(
        trading_id=conf.FAKE_TRADING_ID,
        api_key=conf.FAKE_API_KEY,
        simulation=True,
        lazy_auth=True,
        lazy_symbols=True,
        _base_url_override=FAKE_BASE_URL,
    )


class TestAuthentication:
    def test_authenticates_eagerly_and_keeps_api_host_override_separate(self, respx_mock):
        token_route = respx_mock.post(conf.TOKEN_URL).respond(200, json=conf.CLIENT_TOKEN_RESPONSE)
        with Client(
            trading_id=conf.FAKE_TRADING_ID,
            api_key=conf.FAKE_API_KEY,
            lazy_symbols=True,
            _base_url_override=FAKE_BASE_URL,
        ) as client:
            assert client._base_url == FAKE_BASE_URL
        assert token_route.call_count == 1

    def test_rest_uses_new_token(self, respx_mock):
        client = _make_client(respx_mock)
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").respond(
            200, json={"data": {}}
        )
        try:
            client.account_info()
        finally:
            client.close()
        assert route.calls.last.request.headers["Authorization"] == (
            f"Bearer {conf.FAKE_CLIENT_TOKEN}"
        )

    @pytest.mark.parametrize("internal_request", [False, True])
    def test_401_reauthenticates_once_and_updates_streaming(self, respx_mock, internal_request):
        client = _make_client(respx_mock)
        token_route = respx_mock.post(conf.TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json=conf.CLIENT_TOKEN_RESPONSE),
                httpx.Response(
                    200, json={**conf.CLIENT_TOKEN_RESPONSE, "accessToken": "new-token"}
                ),
            ]
        )
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").mock(
            side_effect=[httpx.Response(401), httpx.Response(200, json={"data": {}})]
        )
        client.streaming.update_token = MagicMock()
        try:
            if internal_request:
                client._request("GET", "/api/account-utils/GetAccountInfo")
            else:
                client.account_info()
        finally:
            client.close()
        assert token_route.call_count == 2
        assert route.call_count == 2
        assert route.calls[0].request.headers["Authorization"] == (
            f"Bearer {conf.FAKE_CLIENT_TOKEN}"
        )
        assert route.calls[1].request.headers["Authorization"] == "Bearer new-token"
        client.streaming.update_token.assert_called_with("new-token")

    def test_second_401_is_not_retried(self, respx_mock):
        client = _make_client(respx_mock)
        token_route = respx_mock.post(conf.TOKEN_URL).respond(200, json=conf.CLIENT_TOKEN_RESPONSE)
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").respond(401)
        try:
            with pytest.raises(Unauthorized):
                client.account_info()
        finally:
            client.close()
        assert route.call_count == 2
        assert token_route.call_count == 2

    def test_failed_reauthentication_does_not_retry_api_request(self, respx_mock):
        client = _make_client(respx_mock)
        token_route = respx_mock.post(conf.TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json=conf.CLIENT_TOKEN_RESPONSE),
                httpx.Response(401, json={"message": "Rejected"}),
            ]
        )
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").respond(401)
        try:
            with pytest.raises(AuthError, match="HTTP 401: Rejected"):
                client.account_info()
        finally:
            client.close()
        assert route.call_count == 1
        assert token_route.call_count == 2

    @pytest.mark.parametrize("seconds_left", [-1, 299])
    def test_rest_refreshes_expiring_token_and_notifies_streaming(self, respx_mock, seconds_left):
        client = _make_client(respx_mock)
        client._auth._token = _TokenRecord(
            "old-token", expires_in=seconds_left, token_type="Bearer"
        )
        client.streaming.update_token = MagicMock()
        token_route = respx_mock.post(conf.TOKEN_URL).respond(200, json=conf.CLIENT_TOKEN_RESPONSE)
        respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").respond(
            200, json={"data": {}}
        )
        try:
            client.account_info()
        finally:
            client.close()
        assert token_route.call_count == 1
        client.streaming.update_token.assert_called_with(conf.FAKE_CLIENT_TOKEN)


class TestPositions:
    def test_positions_sends_market_id_and_parses_real_payload(self, respx_mock):
        client = _make_client(respx_mock)
        positions_route = respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json=RAW_POSITIONS_RESPONSE)
        )

        try:
            positions = client.positions()
        finally:
            client.close()

        assert positions_route.calls.last.request.url.params["MarketId"] == "1"
        assert len(positions) == 4
        stock_ids = {pos.stock_id for pos in positions}
        assert stock_ids == {294, 319, 536, 104879}

        fwry = next(pos for pos in positions if pos.stock_id == 104879)
        assert fwry.name == "Fawry for Banks Tec"
        assert fwry.quantity == 1
        assert fwry.average_price == 21.831
        assert fwry.market_price == 18.99
        # FIXED: Position.symbol now resolves via AliasChoices("ReuterID",
        # "reuterID") and strips the exchange suffix, same convention as
        # SymbolCache.load / endpoints/market_data.py ("FWRY.CA" -> "FWRY").
        assert fwry.symbol == "FWRY"

        by_symbol = {pos.symbol: pos.stock_id for pos in positions}
        assert by_symbol == {"EAST": 294, "ABUK": 319, "COMI": 536, "FWRY": 104879}

    def test_positions_uses_explicit_market_id(self, respx_mock):
        client = _make_client(respx_mock)
        positions_route = respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json=RAW_POSITIONS_RESPONSE)
        )

        try:
            client.positions(market_id=2)
        finally:
            client.close()

        assert positions_route.calls.last.request.url.params["MarketId"] == "2"

    def test_position_finds_matching_symbol(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json=RAW_POSITIONS_RESPONSE)
        )
        # Pre-load the symbol cache directly (bypassing HTTP) so FWRY resolves
        # to the same stockId used in RAW_POSITIONS_RESPONSE.
        client._symbols.load(
            [{"stockId": 104879, "symbol": "FWRY", "reuterCode": "FWRY.CA", "marketId": 1}]
        )

        try:
            pos = client.position("FWRY")
        finally:
            client.close()

        assert pos is not None
        assert pos.stock_id == 104879
        assert pos.name == "Fawry for Banks Tec"
        assert pos.symbol == "FWRY"


class TestPositionsSplit:
    def test_splits_stocks_and_funds_by_fund_id_cross_reference(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json=RAW_POSITIONS_RESPONSE)
        )
        # Confirmed live 2026-09-09: fund rows on GetStocksPortfolio have
        # isFund=False (unreliable) — mock reflects that on purpose to prove
        # the split doesn't rely on it. securityID 104879 (really FWRY, a
        # stock) is used here as the "fund" id purely to test the
        # cross-reference logic in isolation from real data.
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"securityID": 104879, "securityName": "Fake Fund"},
                    ]
                },
            )
        )

        try:
            stocks, funds = client.positions_split()
        finally:
            client.close()

        stock_ids = {pos.stock_id for pos in stocks}
        fund_ids = {pos.stock_id for pos in funds}
        assert stock_ids == {294, 319, 536}
        assert fund_ids == {104879}
        # The "fund" row's is_fund is still False in the mock — proves the
        # split ignored it rather than trusting it.
        assert funds[0].is_fund is False

    def test_all_stocks_when_no_funds_held(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json=RAW_POSITIONS_RESPONSE)
        )
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        try:
            stocks, funds = client.positions_split()
        finally:
            client.close()

        assert len(stocks) == 4
        assert funds == []

    def test_uses_explicit_market_id(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json=RAW_POSITIONS_RESPONSE)
        )
        funds_route = respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/2").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        try:
            client.positions_split(market_id=2)
        finally:
            client.close()

        assert funds_route.called


class TestFundPositions:
    def test_fund_positions_sends_market_id_and_filters_isfund(self, respx_mock):
        client = _make_client(respx_mock)
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(200, json=RAW_PORTFOLIO_SECURITIES_RESPONSE)
        )

        try:
            fund_positions = client.fund_positions()
        finally:
            client.close()

        assert route.calls.last.request.url.params["marketId"] == "1"
        # Only the isFund=true row should come through, not the stock row.
        assert len(fund_positions) == 1

        fund = fund_positions[0]
        assert fund.fund_id == 9001
        assert fund.symbol == "SIGP"
        assert fund.name == "Some Income Fund"
        assert fund.fund_type == "Money Market"
        assert fund.quantity == 10
        assert fund.average_price == 100.0
        assert fund.market_price == 101.5
        assert fund.market_value == 1015.0
        assert fund.unrealized_pnl == 15.0
        assert fund.unrealized_pnl_pct == 1.5
        assert fund.is_invest is True
        assert fund.is_redeem is False
        assert fund.currency == "EGP"

    def test_fund_positions_uses_explicit_market_id(self, respx_mock):
        client = _make_client(respx_mock)
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(200, json=RAW_PORTFOLIO_SECURITIES_RESPONSE)
        )

        try:
            client.fund_positions(market_id=2)
        finally:
            client.close()

        assert route.calls.last.request.url.params["marketId"] == "2"

    def test_fund_positions_empty_when_no_securities(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(
                200,
                json={
                    "messages": None,
                    "data": {"securityPositions": None, "stocks": None, "funds": None},
                },
            )
        )

        try:
            fund_positions = client.fund_positions()
        finally:
            client.close()

        assert fund_positions == []

    def test_fund_position_finds_matching_fund_id(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(200, json=RAW_PORTFOLIO_SECURITIES_RESPONSE)
        )

        try:
            fund = client.fund_position(9001)
            missing = client.fund_position(424242)
        finally:
            client.close()

        assert fund is not None
        assert fund.fund_id == 9001
        assert fund.name == "Some Income Fund"
        assert missing is None


def _mock_same_day_list(respx_mock, market_id: int = 1, member_stock_ids: set[int] | None = None):
    """Mock the two live calls list_stocks() makes to resolve
    is_same_day_eligible (stock-lists-types + stocks-by-list-type for the
    Intraday category)."""
    member_stock_ids = member_stock_ids or set()
    respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-lists-types/{market_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "messages": None,
                "data": [{"name": "Intraday Stocks", "id": 2, "count": 2, "type": 2}],
            },
        )
    )
    respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-by-list-type/2/2/{market_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "messages": None,
                "data": [
                    {
                        "id": sid,
                        "reuterCode": f"S{sid}.CA",
                        "name": f"Stock {sid}",
                        "marketId": market_id,
                    }
                    for sid in member_stock_ids
                ],
            },
        )
    )


class TestListStocks:
    def test_no_market_id_matches_explicit_market_id_1(self, respx_mock):
        _mock_same_day_list(respx_mock, member_stock_ids={101})
        client = _make_client(respx_mock)
        try:
            default_result = client.list_stocks()
            explicit_result = client.list_stocks(market_id=1)
        finally:
            client.close()

        assert default_result == explicit_result
        assert len(default_result) == 1
        assert default_result[0].symbol == "COMI"

    def test_enriches_security_class_for_known_stock_id(self, respx_mock, monkeypatch):
        """TEMPORARY scaffolding: list_stocks() enriches from the
        client-side security-class snapshot (see
        younit._security_class_snapshot)."""
        _mock_same_day_list(respx_mock, member_stock_ids={101})
        monkeypatch.setattr(
            client_module._security_class_snapshot,
            "get_security_class",
            lambda stock_id: (1, "LocalSecurity_IN") if stock_id == 101 else (None, None),
        )
        client = _make_client(respx_mock)

        try:
            result = client.list_stocks()
        finally:
            client.close()

        assert result[0].stock_id == 101
        assert result[0].security_class_id == 1
        assert result[0].security_class_name == "LocalSecurity_IN"

    def test_security_class_none_for_unknown_stock_id(self, respx_mock, monkeypatch):
        _mock_same_day_list(respx_mock, member_stock_ids={101})
        monkeypatch.setattr(
            client_module._security_class_snapshot,
            "get_security_class",
            lambda stock_id: (None, None),
        )
        client = _make_client(respx_mock)

        try:
            result = client.list_stocks()
        finally:
            client.close()

        assert result[0].security_class_id is None
        assert result[0].security_class_name is None

    def test_security_class_snapshot_captured_at_exposed(self, respx_mock, monkeypatch):
        monkeypatch.setattr(
            client_module._security_class_snapshot,
            "snapshot_captured_at",
            lambda: "2026-09-29T00:00:00+00:00",
        )
        client = _make_client(respx_mock)

        try:
            captured_at = client.security_class_snapshot_captured_at
        finally:
            client.close()

        assert captured_at == "2026-09-29T00:00:00+00:00"


RAW_STOCK_LIST_TYPES = [
    {"name": "Intraday Stocks", "description": "...", "id": 2, "count": 2, "type": 2},
    {"name": "OTC Stocks", "description": "...", "id": 3, "count": 1, "type": 3},
    {"name": "Most Liked Stocks", "description": "...", "id": 5, "count": 10, "type": 5},
]

RAW_INTRADAY_STOCKS = [
    {"id": 101, "reuterCode": "COMI.CA", "name": "Commercial International Bank", "marketId": 1},
    {"id": 102, "reuterCode": "EAST.CA", "name": "Eastern Company", "marketId": 1},
]


class TestListStocksSameDayEligibility:
    """list_stocks() enriches is_same_day_eligible from live Intraday-list
    membership (folded in from the removed list_tradeable_stocks())."""

    def test_marks_true_for_intraday_list_member(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-lists-types/1").mock(
            return_value=httpx.Response(200, json={"messages": None, "data": RAW_STOCK_LIST_TYPES})
        )
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-by-list-type/2/2/1").mock(
            return_value=httpx.Response(200, json={"messages": None, "data": RAW_INTRADAY_STOCKS})
        )

        try:
            stocks = client.list_stocks()
        finally:
            client.close()

        # _make_client's base mock returns only COMI (stock_id 101), which
        # IS present in the mocked Intraday list above.
        assert len(stocks) == 1
        assert stocks[0].stock_id == 101
        assert stocks[0].is_same_day_eligible is True

    def test_marks_false_for_non_member(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-lists-types/1").mock(
            return_value=httpx.Response(200, json={"messages": None, "data": RAW_STOCK_LIST_TYPES})
        )
        # Intraday list does NOT include stock_id 101 (COMI) this time.
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-by-list-type/2/2/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "messages": None,
                    "data": [{"id": 999, "reuterCode": "XYZ.CA", "name": "Other", "marketId": 1}],
                },
            )
        )

        try:
            stocks = client.list_stocks()
        finally:
            client.close()

        assert stocks[0].is_same_day_eligible is False

    def test_uses_explicit_market_id(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/market/2").mock(
            return_value=httpx.Response(200, json=RAW_STOCKS)
        )
        types_route = respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-lists-types/2").mock(
            return_value=httpx.Response(200, json={"messages": None, "data": RAW_STOCK_LIST_TYPES})
        )
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-by-list-type/2/2/2").mock(
            return_value=httpx.Response(200, json={"messages": None, "data": RAW_INTRADAY_STOCKS})
        )

        try:
            client.list_stocks(market_id=2)
        finally:
            client.close()

        assert types_route.calls.last.request.url.path.endswith("/stock-lists-types/2")

    def test_missing_category_logged_and_defaults_false(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        # Intraday category is deliberately absent from this response.
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-lists-types/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "messages": None,
                    "data": [{"name": "Most Liked Stocks", "id": 5, "count": 10, "type": 5}],
                },
            )
        )
        log_spy = MagicMock()
        monkeypatch.setattr(client_module, "_log", log_spy)

        try:
            stocks = client.list_stocks()
        finally:
            client.close()

        assert stocks[0].is_same_day_eligible is False
        log_spy.warning.assert_called_once_with(
            "list_stocks_same_day_category_not_found", market_id=1
        )


RAW_MULTI_CLASS_STOCKS = [
    {"stockId": 101, "symbol": "AAA", "stockName": "AAA Co", "reuterCode": "AAA.CA", "marketId": 1},
    {"stockId": 102, "symbol": "BBB", "stockName": "BBB Co", "reuterCode": "BBB.CA", "marketId": 1},
    {"stockId": 103, "symbol": "CCC", "stockName": "CCC Co", "reuterCode": "CCC.CA", "marketId": 1},
    {"stockId": 104, "symbol": "DDD", "stockName": "DDD Co", "reuterCode": "DDD.CA", "marketId": 1},
]

# 101 -> LocalSecurity_IN, 102 -> OTC, 103 -> Tbills, 104 -> not in snapshot (None).
_MULTI_CLASS_MAP = {
    101: (1, "LocalSecurity_IN"),
    102: (5, "OTC"),
    103: (35, "Tbills"),
}


class TestListByClassAndConvenienceFilters:
    """list_by_class()/list_same_day_eligible()/list_otc() — thin,
    in-memory filters over a single list_stocks() call."""

    def _make_filterable_client(self, respx_mock, monkeypatch, same_day_stock_ids=frozenset({101})):
        monkeypatch.setattr(
            client_module._security_class_snapshot,
            "get_security_class",
            lambda stock_id: _MULTI_CLASS_MAP.get(stock_id, (None, None)),
        )
        _mock_same_day_list(respx_mock, member_stock_ids=set(same_day_stock_ids))
        return _make_client(respx_mock, raw_stocks=RAW_MULTI_CLASS_STOCKS)

    def test_list_by_class_single_class(self, respx_mock, monkeypatch):
        client = self._make_filterable_client(respx_mock, monkeypatch)

        try:
            result = client.list_by_class("OTC")
        finally:
            client.close()

        assert {s.stock_id for s in result} == {102}

    def test_list_by_class_multiple_classes_is_or_logic(self, respx_mock, monkeypatch):
        client = self._make_filterable_client(respx_mock, monkeypatch)

        try:
            result = client.list_by_class("OTC", "Tbills")
        finally:
            client.close()

        assert {s.stock_id for s in result} == {102, 103}

    def test_list_by_class_excludes_none_security_class_name(self, respx_mock, monkeypatch):
        client = self._make_filterable_client(respx_mock, monkeypatch)

        try:
            result = client.list_by_class("OTC", "Tbills", "LocalSecurity_IN")
        finally:
            client.close()

        # stock_id 104 has security_class_name=None (not in the snapshot) —
        # never included, even though every recognized class is requested.
        assert 104 not in {s.stock_id for s in result}
        assert {s.stock_id for s in result} == {101, 102, 103}

    def test_list_by_class_unrecognized_name_raises_value_error(self, respx_mock, monkeypatch):
        client = self._make_filterable_client(respx_mock, monkeypatch)

        try:
            with pytest.raises(ValueError, match="Unrecognized security_class_name"):
                client.list_by_class("NotARealClass")
        finally:
            client.close()

    def test_list_same_day_eligible(self, respx_mock, monkeypatch):
        client = self._make_filterable_client(
            respx_mock, monkeypatch, same_day_stock_ids={101, 103}
        )

        try:
            result = client.list_same_day_eligible()
        finally:
            client.close()

        assert {s.stock_id for s in result} == {101, 103}

    def test_list_otc(self, respx_mock, monkeypatch):
        client = self._make_filterable_client(respx_mock, monkeypatch)

        try:
            result = client.list_otc()
        finally:
            client.close()

        assert {s.stock_id for s in result} == {102}


class TestCancelOrderProfileResolution:
    def test_uses_cached_profile_id_when_not_provided(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        client._cached_profile_id = 555
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal/123/cancel").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )
        get_order_spy = MagicMock()
        monkeypatch.setattr(client, "get_order", get_order_spy)

        try:
            result = client.cancel_order(123)
        finally:
            client.close()

        assert result is True
        get_order_spy.assert_not_called()

    def test_falls_back_to_get_profile_id_when_not_cached(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal/123/cancel").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )
        get_profile_id_spy = MagicMock(return_value=999)
        monkeypatch.setattr(client, "_get_profile_id", get_profile_id_spy)

        try:
            result = client.cancel_order(123)
        finally:
            client.close()

        assert result is True
        get_profile_id_spy.assert_called_once()

    def test_raises_invalid_order_when_no_profile_id_available(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        get_order_spy = MagicMock()
        monkeypatch.setattr(client, "get_order", get_order_spy)
        monkeypatch.setattr(client, "_get_profile_id", MagicMock(return_value=None))

        try:
            with pytest.raises(InvalidOrder, match="No profile_id available"):
                client.cancel_order(123)
        finally:
            client.close()

        get_order_spy.assert_not_called()


class TestAmendOrderProfileResolution:
    def test_uses_cached_profile_id_when_not_provided(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        client._cached_profile_id = 777
        respx_mock.patch(f"{FAKE_BASE_URL}/api/v1/orders/normal/456").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )
        get_order_spy = MagicMock()
        monkeypatch.setattr(client, "get_order", get_order_spy)

        try:
            result = client.amend_order(456, price=20.0)
        finally:
            client.close()

        assert result is True
        get_order_spy.assert_not_called()

    def test_falls_back_to_get_profile_id_when_not_cached(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        respx_mock.patch(f"{FAKE_BASE_URL}/api/v1/orders/normal/456").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )
        get_profile_id_spy = MagicMock(return_value=888)
        monkeypatch.setattr(client, "_get_profile_id", get_profile_id_spy)

        try:
            result = client.amend_order(456, price=20.0)
        finally:
            client.close()

        assert result is True
        get_profile_id_spy.assert_called_once()


class TestProfileIdProperty:
    def test_resolves_and_caches_across_repeated_access(self, respx_mock):
        client = _make_client(respx_mock)
        buying_power_route = respx_mock.get(
            f"{FAKE_BASE_URL}/api/v1/trading/buying-power/normal/101"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"profileID": 4242, "rawValue": 1000.0}, "messages": []},
            )
        )

        try:
            first = client.profile_id
            second = client.profile_id
        finally:
            client.close()

        assert first == 4242
        assert second == 4242
        assert buying_power_route.call_count == 1

    def test_lazy_loads_symbol_cache_on_fresh_client(self, respx_mock):
        """Client is constructed with lazy_symbols=True by _make_client and no
        prior list_stocks()/resolve() call is made before accessing profile_id.
        """
        client = _make_client(respx_mock)
        stocks_route = respx_mock["market_stocks"]
        buying_power_route = respx_mock.get(
            f"{FAKE_BASE_URL}/api/v1/trading/buying-power/normal/101"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"data": {"profileID": 4242, "rawValue": 1000.0}, "messages": []},
            )
        )

        assert not client._symbols.is_loaded

        try:
            result = client.profile_id
        finally:
            client.close()

        assert result == 4242
        assert stocks_route.call_count == 1
        assert buying_power_route.call_count == 1

    def test_raises_invalid_order_when_no_profile_id_available(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        get_order_spy = MagicMock()
        monkeypatch.setattr(client, "get_order", get_order_spy)
        monkeypatch.setattr(client, "_get_profile_id", MagicMock(return_value=None))

        try:
            with pytest.raises(InvalidOrder, match="No profile_id available"):
                client.amend_order(456, price=20.0)
        finally:
            client.close()

        get_order_spy.assert_not_called()


class TestPlaceOrder:
    """POST /api/v1/orders/normal now returns the real orderId directly.

    Raw shape confirmed live 2026-09-02 (real market buy, 1 x EGCH):
    {"messages": [""], "status": 1, "data": {"result": true, "orderId": 54250949}}
    — replacing the old {"messages": [...], "status": 1, "data": true} shape
    that never carried an order ID.
    """

    NEW_SHAPE_RESPONSE: ClassVar[dict] = {
        "messages": [""],
        "status": 1,
        "data": {"result": True, "orderId": 54250949},
    }

    def _mock_buying_power(self, respx_mock):
        return respx_mock.get(f"{FAKE_BASE_URL}/api/v1/trading/buying-power/normal/101").mock(
            return_value=httpx.Response(
                200, json={"data": {"profileID": 4242, "rawValue": 1000.0}, "messages": []}
            )
        )

    def test_market_order_populates_order_id_without_confirm(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            # confirm=False: isolate this to the placement call, no get_order.
            order = client.buy(symbol="COMI", qty=1, limit=None, confirm=False)
        finally:
            client.close()

        # order_id is now populated immediately, regardless of confirm.
        assert order.order_id == 54250949
        assert order.is_market_price is True

        body = json.loads(order_route.calls.last.request.content)
        # Market-order fix: price=0 explicit, orderExpireTermsID=2, and
        # executionInstructionId/isEdit omitted entirely.
        assert body["price"] == 0
        assert body["orderExpireTermsID"] == 2
        assert "executionInstructionId" not in body
        assert "isEdit" not in body

    def test_limit_order_body_unchanged_but_order_id_still_populated(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"minPrice": 0, "maxPrice": 0, "isIntraday": False, "isTPlus1": False}
                },
            )
        )
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            order = client.buy(symbol="COMI", qty=1, limit=65.0, confirm=False)
        finally:
            client.close()

        assert order.order_id == 54250949

        body = json.loads(order_route.calls.last.request.content)
        # Limit orders are completely unaffected by the market-order fix.
        assert body["price"] == 65.0
        assert body["orderExpireTermsID"] == int(OrderExpireTerm.DAY)
        assert body["executionInstructionId"] == 1
        assert body["isEdit"] is False

    def test_confirm_true_calls_list_orders_directly_no_streaming(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )
        list_orders_spy = MagicMock(
            return_value=[{"OrderId": 54250949, "Status": "Accepted", "StockId": 101}]
        )
        monkeypatch.setattr(client, "list_orders", list_orders_spy)
        # get_order() is confirmed to never carry status, so place_order()
        # must not call it at all anymore.
        get_order_spy = MagicMock(side_effect=AssertionError("get_order() should not be called"))
        monkeypatch.setattr(client, "get_order", get_order_spy)
        subscribe_spy = MagicMock()
        monkeypatch.setattr(client.streaming, "subscribe_orders", subscribe_spy)

        try:
            result = client.buy(symbol="COMI", qty=1, limit=None, confirm=True)
        finally:
            client.close()

        list_orders_spy.assert_called_once_with(profile_id=4242)
        get_order_spy.assert_not_called()
        subscribe_spy.assert_not_called()
        assert result.order_id == 54250949
        assert result.status_text == "Accepted"

    def test_confirm_defaults_to_true_calls_list_orders_without_passing_it(
        self, respx_mock, monkeypatch
    ):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )
        list_orders_spy = MagicMock(
            return_value=[{"OrderId": 54250949, "Status": "Accepted", "StockId": 101}]
        )
        monkeypatch.setattr(client, "list_orders", list_orders_spy)

        try:
            # confirm not passed at all — new default (True) should still
            # trigger the direct list_orders() call.
            result = client.buy(symbol="COMI", qty=1, limit=None)
        finally:
            client.close()

        list_orders_spy.assert_called_once_with(profile_id=4242)
        assert result.order_id == 54250949
        assert result.status_text == "Accepted"

    def test_list_orders_match_populates_real_status(self, respx_mock, monkeypatch):
        """confirm=True's list_orders() lookup surfaces real status/fields.

        Unlike the old get_order()-then-order_history() fallback, this call
        happens unconditionally on every confirm=True placement — list_orders()
        was live-verified to be cheap/scoped, unlike order_history().
        """
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )
        list_orders_spy = MagicMock(
            return_value=[
                {
                    "OrderId": 54250949,
                    "StockId": 101,
                    "Quantity": 1,
                    "Price": None,
                    "OrderTypeName": "Buy",
                    "ReuterId": "COMI.CA",
                    "Status": "Accepted",
                    "Average": 64.5,
                    "ExecutedQty": 1,
                }
            ]
        )
        monkeypatch.setattr(client, "list_orders", list_orders_spy)

        try:
            result = client.buy(symbol="COMI", qty=1, limit=None, confirm=True)
        finally:
            client.close()

        # profile_id already resolved earlier in place_order() — passed
        # explicitly rather than letting list_orders() re-resolve it.
        list_orders_spy.assert_called_once_with(profile_id=4242)
        assert result.order_id == 54250949
        assert result.stock_id == 101
        # Real status/average fill price/symbol are only available via this
        # lookup — the placement stub doesn't carry them.
        assert result.status_text == "Accepted"
        assert result.average_price == 64.5
        assert result.symbol == "COMI"
        assert result.filled_quantity == 1

    def test_list_orders_no_match_falls_back_to_stub(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )
        list_orders_spy = MagicMock(return_value=[])
        monkeypatch.setattr(client, "list_orders", list_orders_spy)

        try:
            result = client.buy(symbol="COMI", qty=1, limit=None, confirm=True)
        finally:
            client.close()

        list_orders_spy.assert_called_once_with(profile_id=4242)
        assert result.order_id == 54250949
        assert result.is_market_price is True
        assert result.status_text is None

    def test_list_orders_failure_falls_back_to_stub(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )
        monkeypatch.setattr(
            client, "list_orders", MagicMock(side_effect=APIError("boom", status_code=500))
        )

        try:
            result = client.buy(symbol="COMI", qty=1, limit=None, confirm=True)
        finally:
            client.close()

        assert result.order_id == 54250949
        assert result.status_text is None

    def test_list_orders_defaults_profile_id_and_market_id(self, respx_mock):
        client = _make_client(respx_mock)
        client._cached_profile_id = 4242
        route = respx_mock.post(f"{FAKE_BASE_URL}/core-services/Orders").mock(
            return_value=httpx.Response(200, json=[{"OrderId": 1, "Status": "Accepted"}])
        )

        try:
            rows = client.list_orders()
        finally:
            client.close()

        assert rows == [{"OrderId": 1, "Status": "Accepted"}]
        body = json.loads(route.calls.last.request.content)
        assert body["ProfileIds"] == [4242]
        assert body["MarketId"] == 1

    def test_result_false_raises_order_rejected(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(
                200,
                json={
                    "messages": ["Order Suspend Compliance"],
                    "status": 1,
                    "data": {"result": False},
                },
            )
        )

        try:
            with pytest.raises(OrderRejected, match="Order Suspend Compliance"):
                client.buy(symbol="COMI", qty=1, limit=None)
        finally:
            client.close()


class TestConfirmDefaultsToTrue:
    """confirm now defaults to True on every stock order-placement method."""

    @pytest.mark.parametrize(
        "method_name",
        ["buy", "sell", "buy_market", "buy_limit", "sell_market", "sell_limit", "place_order"],
    )
    def test_confirm_default_is_true(self, method_name):
        sig = inspect.signature(getattr(Client, method_name))
        assert sig.parameters["confirm"].default is True


class TestSellSettlement:
    """sell()'s settlement param maps a friendly string to OperationType.

    Mirrors the ``expire`` string convention ("day"/"gtd") instead of taking
    the raw enum directly.
    """

    NEW_SHAPE_RESPONSE: ClassVar[dict] = {
        "messages": [""],
        "status": 1,
        "data": {"result": True, "orderId": 54250949},
    }

    def _mock_buying_power(self, respx_mock):
        return respx_mock.get(f"{FAKE_BASE_URL}/api/v1/trading/buying-power/normal/101").mock(
            return_value=httpx.Response(
                200, json={"data": {"profileID": 4242, "rawValue": 1000.0}, "messages": []}
            )
        )

    def test_sell_defaults_to_t2(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.sell(symbol="COMI", qty=1, limit=None, confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["operationType"] == int(OperationType.SELL) == 200

    def test_settlement_t0_sends_201(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.sell(symbol="COMI", qty=1, limit=None, settlement="t0", confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["operationType"] == int(OperationType.SELL_SAME_DAY) == 201

    def test_settlement_same_day_is_alias_for_t0(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.sell(symbol="COMI", qty=1, limit=None, settlement="same_day", confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["operationType"] == int(OperationType.SELL_SAME_DAY) == 201

    def test_settlement_t1_sends_203(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.sell(symbol="COMI", qty=1, limit=None, settlement="t1", confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["operationType"] == int(OperationType.SELL_T1) == 203

    def _mock_stock_trading_info(self, respx_mock):
        return respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"minPrice": 0, "maxPrice": 0, "isIntraday": False, "isTPlus1": False}
                },
            )
        )

    def test_settlement_t0_limit_sends_expire_term_2_no_expire_date(self, respx_mock):
        """Confirmed live 2026-09-29: DAY(7) and GOOD_TILL_DATE(8) are both
        rejected for same-day settlement limit sells — UNKNOWN_2 (the same
        value required for market orders) is the one that's accepted, with
        no expireDate needed."""
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        self._mock_stock_trading_info(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.sell(symbol="COMI", qty=1, limit=65.0, settlement="t0", confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["orderExpireTermsID"] == int(OrderExpireTerm.UNKNOWN_2) == 2
        assert "expireDate" not in body

    @pytest.mark.parametrize("settlement", ["t1", "t2"])
    def test_settlement_t1_t2_limit_still_sends_day_unchanged(self, respx_mock, settlement):
        """Regression guard: only same-day settlement is affected by the
        UNKNOWN_2 fix — t1/t2 limit sells keep using DAY(7) unchanged."""
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        self._mock_stock_trading_info(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.sell(symbol="COMI", qty=1, limit=65.0, settlement=settlement, confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["orderExpireTermsID"] == int(OrderExpireTerm.DAY) == 7

    def test_invalid_settlement_raises_invalid_order(self, respx_mock):
        client = _make_client(respx_mock)

        try:
            with pytest.raises(InvalidOrder, match="Invalid settlement 'bogus'"):
                client.sell(symbol="COMI", qty=1, limit=None, settlement="bogus")
        finally:
            client.close()


class TestMarketOrderAutoExpireDate:
    """Market orders auto-supply expire_date (Africa/Cairo local) when omitted."""

    NEW_SHAPE_RESPONSE: ClassVar[dict] = {
        "messages": [""],
        "status": 1,
        "data": {"result": True, "orderId": 54250949},
    }

    def _mock_buying_power(self, respx_mock):
        return respx_mock.get(f"{FAKE_BASE_URL}/api/v1/trading/buying-power/normal/101").mock(
            return_value=httpx.Response(
                200, json={"data": {"profileID": 4242, "rawValue": 1000.0}, "messages": []}
            )
        )

    def test_market_order_auto_supplies_expire_date_when_none_given(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.buy(symbol="COMI", qty=1, limit=None, confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body.get("expireDate") is not None

    def test_market_order_respects_explicit_expire_date(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )
        explicit = datetime(2026, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Africa/Cairo"))

        try:
            client.sell(symbol="COMI", qty=1, limit=None, expire_date=explicit, confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body["expireDate"].startswith("2026-01-01T12:00:00")

    def test_limit_order_does_not_auto_supply_expire_date(self, respx_mock):
        client = _make_client(respx_mock)
        self._mock_buying_power(respx_mock)
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"minPrice": 0, "maxPrice": 0, "isIntraday": False, "isTPlus1": False}
                },
            )
        )
        order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/normal").mock(
            return_value=httpx.Response(200, json=self.NEW_SHAPE_RESPONSE)
        )

        try:
            client.buy(symbol="COMI", qty=1, limit=65.0, confirm=False)
        finally:
            client.close()

        body = json.loads(order_route.calls.last.request.content)
        assert body.get("expireDate") is None


class TestTradingConvenienceWrappers:
    """buy_market/buy_limit/sell_market/sell_limit are thin wrappers."""

    def test_buy_market_calls_buy_correctly(self):
        client = Client.__new__(Client)
        buy_spy = MagicMock(return_value="order")
        client.buy = buy_spy

        result = client.buy_market("COMI", 5, confirm=True, confirm_timeout=1.0)

        assert result == "order"
        buy_spy.assert_called_once_with("COMI", 5, limit=None, confirm=True, confirm_timeout=1.0)

    def test_buy_limit_calls_buy_correctly(self):
        client = Client.__new__(Client)
        buy_spy = MagicMock(return_value="order")
        client.buy = buy_spy

        result = client.buy_limit("COMI", 5, 65.0, expire="gtd", confirm_timeout=2.0)

        assert result == "order"
        buy_spy.assert_called_once_with(
            "COMI",
            5,
            limit=65.0,
            expire="gtd",
            expire_date=None,
            confirm=True,
            confirm_timeout=2.0,
        )

    def test_sell_market_calls_sell_correctly(self):
        client = Client.__new__(Client)
        sell_spy = MagicMock(return_value="order")
        client.sell = sell_spy

        result = client.sell_market("COMI", 5, settlement="t1", confirm=True)

        assert result == "order"
        sell_spy.assert_called_once_with(
            "COMI", 5, limit=None, settlement="t1", confirm=True, confirm_timeout=10.0
        )

    def test_sell_limit_calls_sell_correctly(self):
        client = Client.__new__(Client)
        sell_spy = MagicMock(return_value="order")
        client.sell = sell_spy

        result = client.sell_limit("COMI", 5, 65.0, settlement="t0", expire="gtd")

        assert result == "order"
        sell_spy.assert_called_once_with(
            "COMI",
            5,
            limit=65.0,
            settlement="t0",
            expire="gtd",
            expire_date=None,
            confirm=True,
            confirm_timeout=10.0,
        )


class TestPlaceFundOrder:
    def test_buy_fund_sends_expected_body(self, respx_mock):
        client = _make_client(respx_mock)
        client._cached_profile_id = 555
        fund_order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": True, "orderId": 54262884}, "messages": []}
            )
        )

        try:
            result = client.buy_fund(42, 10, 100.5)
        finally:
            client.close()

        assert isinstance(result, Order)
        assert result.order_id == 54262884
        assert result.fund_id == 42
        assert result.stock_id is None
        body = json.loads(fund_order_route.calls.last.request.content)
        # Confirmed minimal working body (live-tested 2026-09-02, order
        # 54262884) — exactly these 6 keys, nothing more.
        assert set(body.keys()) == {
            "profileId",
            "fundId",
            "operationType",
            "quantity",
            "price",
            "isIPOFund",
        }
        assert body["profileId"] == 555
        assert body["fundId"] == 42
        assert body["operationType"] == int(OperationType.BUY)
        assert body["quantity"] == 10
        assert body["price"] == 100.5
        # No isMarketPrice field exists for funds — must never be sent.
        assert "isMarketPrice" not in body
        # Confirmed extras are omitted by default, not guessed.
        assert "executionTerm" not in body
        assert "subOrderVia" not in body
        assert "orderVia" not in body
        assert "orderExpireTermsID" not in body

    def test_sell_fund_sets_operation_type(self, respx_mock):
        client = _make_client(respx_mock)
        client._cached_profile_id = 555
        fund_order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": True, "orderId": 1}, "messages": []}
            )
        )

        try:
            client.sell_fund(42, 10, 100.5)
        finally:
            client.close()

        body = json.loads(fund_order_route.calls.last.request.content)
        assert body["operationType"] == int(OperationType.SELL)

    def test_gtd_expire_sets_order_expire_terms_id(self, respx_mock):
        client = _make_client(respx_mock)
        client._cached_profile_id = 555
        fund_order_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": True, "orderId": 1}, "messages": []}
            )
        )

        try:
            client.buy_fund(42, 10, 100.5, expire="gtd")
        finally:
            client.close()

        body = json.loads(fund_order_route.calls.last.request.content)
        assert body["orderExpireTermsID"] == int(OrderExpireTerm.GOOD_TILL_DATE)

    def test_falls_back_to_get_profile_id_when_not_cached(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": True, "orderId": 1}, "messages": []}
            )
        )
        get_profile_id_spy = MagicMock(return_value=999)
        monkeypatch.setattr(client, "_get_profile_id", get_profile_id_spy)

        try:
            result = client.buy_fund(42, 10, 100.5)
        finally:
            client.close()

        assert isinstance(result, Order)
        assert result.order_id == 1
        get_profile_id_spy.assert_called_once()

    def test_raises_invalid_order_when_qty_not_positive(self, respx_mock):
        client = _make_client(respx_mock)

        try:
            with pytest.raises(InvalidOrder, match="qty must be a positive integer"):
                client.buy_fund(42, 0, 100.5)
        finally:
            client.close()

    def test_raises_invalid_order_when_no_profile_id_available(self, respx_mock, monkeypatch):
        client = _make_client(respx_mock)
        monkeypatch.setattr(client, "_get_profile_id", MagicMock(return_value=None))

        try:
            with pytest.raises(InvalidOrder, match="No profile_id available"):
                client.buy_fund(42, 10, 100.5)
        finally:
            client.close()

    def test_raises_order_rejected_on_failure_response(self, respx_mock):
        client = _make_client(respx_mock)
        client._cached_profile_id = 555
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(
                200, json={"data": {"result": False}, "messages": ["insufficient funds"]}
            )
        )

        try:
            with pytest.raises(OrderRejected, match="insufficient funds"):
                client.buy_fund(42, 10, 100.5)
        finally:
            client.close()

    def test_raises_api_error_when_order_id_missing(self, respx_mock):
        client = _make_client(respx_mock)
        client._cached_profile_id = 555
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund").mock(
            return_value=httpx.Response(200, json={"data": {"result": True}, "messages": []})
        )

        try:
            with pytest.raises(APIError, match="did not include an orderId"):
                client.buy_fund(42, 10, 100.5)
        finally:
            client.close()


class TestAmendFundOrder:
    def test_sends_only_quantity_and_price_no_profile_id(self, respx_mock):
        client = _make_client(respx_mock)
        fund_amend_route = respx_mock.patch(f"{FAKE_BASE_URL}/api/v1/orders/fund/789").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )

        try:
            result = client.amend_fund_order(789, qty=15, price=22.5)
        finally:
            client.close()

        assert result is True
        body = json.loads(fund_amend_route.calls.last.request.content)
        assert body == {"quantity": 15, "price": 22.5}

    def test_raises_order_rejected_on_failure_response(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.patch(f"{FAKE_BASE_URL}/api/v1/orders/fund/789").mock(
            return_value=httpx.Response(200, json={"data": False, "messages": ["order not found"]})
        )

        try:
            with pytest.raises(OrderRejected, match="order not found"):
                client.amend_fund_order(789, price=22.5)
        finally:
            client.close()


class TestCancelFundOrder:
    def test_calls_dedicated_fund_cancel_endpoint_no_body(self, respx_mock):
        client = _make_client(respx_mock)
        cancel_route = respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund/54262884/cancel").mock(
            return_value=httpx.Response(200, json={"data": True, "messages": []})
        )

        try:
            result = client.cancel_fund_order(54262884)
        finally:
            client.close()

        assert result is True
        assert cancel_route.calls.last.request.content in (b"", None)

    def test_raises_order_rejected_on_failure_response(self, respx_mock):
        client = _make_client(respx_mock)
        respx_mock.post(f"{FAKE_BASE_URL}/api/v1/orders/fund/789/cancel").mock(
            return_value=httpx.Response(200, json={"data": False, "messages": ["order not found"]})
        )

        try:
            with pytest.raises(OrderRejected, match="order not found"):
                client.cancel_fund_order(789)
        finally:
            client.close()


class _FakeStreamingClient:
    """Minimal stand-in for StreamingClient.subscribe_market/unsubscribe."""

    def __init__(self, status: str | None = None, respond: bool = True):
        self._status = status
        self._respond = respond
        self.subscribed_market_id: int | None = None
        self.unsubscribed_subs: list[object] = []

    def subscribe_market(self, market_id, on_update, on_error):
        self.subscribed_market_id = market_id
        if self._respond:
            on_update(MarketUpdate({"m_MarketStatus": self._status}))
        return object()

    def unsubscribe(self, subscription):
        self.unsubscribed_subs.append(subscription)


class TestMarketStatus:
    """market_status() maps the MarketStatistics stream's m_MarketStatus field."""

    def _make_bare_client(self, status: str | None = None, respond: bool = True):
        client = Client.__new__(Client)
        client._settings = MagicMock(default_market_id=1)
        client.streaming = _FakeStreamingClient(status=status, respond=respond)
        return client

    def test_status_2_maps_to_open(self):
        client = self._make_bare_client(status="2")

        assert client.market_status() == "open"
        assert client.streaming.subscribed_market_id == 1
        assert len(client.streaming.unsubscribed_subs) == 1

    def test_status_3_maps_to_closed(self):
        client = self._make_bare_client(status="3")

        assert client.market_status() == "closed"

    def test_unrecognized_status_maps_to_unknown(self):
        client = self._make_bare_client(status="7")

        assert client.market_status() == "unknown"

    def test_no_update_within_timeout_returns_unreachable(self):
        client = self._make_bare_client(respond=False)

        assert client.market_status(timeout=0.05) == "unreachable"
        assert len(client.streaming.unsubscribed_subs) == 1

    def test_market_id_override_is_forwarded(self):
        client = self._make_bare_client(status="2")

        client.market_status(market_id=7)

        assert client.streaming.subscribed_market_id == 7


class _FakeStreamingClientForGetTopMovers:
    """Minimal stand-in for StreamingClient.subscribe_quote/unsubscribe.

    Simulates snapshot-burst delivery: subscribe_quote synchronously invokes
    on_update (mimicking a real snapshot arriving near-instantly), UNLESS the
    symbol is in ``unresponsive_symbols`` (simulates a laggard that never
    responds, for timeout testing). Also mirrors the real
    StreamingClient.unsubscribe's composite-handle recursion, and tracks how
    many subscriptions are open at once (incremented on subscribe, decremented
    on unsubscribe) so tests can assert get_top_movers() never exceeds its
    `limit` concurrently, even while covering the full stock universe across
    multiple batches.
    """

    def __init__(
        self,
        quotes: dict[str, SymbolUpdate] | None = None,
        unresponsive_symbols: set[str] | None = None,
    ):
        self.quotes = quotes or {}
        self.unresponsive_symbols = unresponsive_symbols or set()
        self.subscribed_symbols: list[str] = []
        self.unsubscribed_subs: list[object] = []
        self._currently_open = 0
        self.max_concurrent_open = 0

    def subscribe_quote(self, symbol, on_update, on_error=None):
        self.subscribed_symbols.append(symbol)
        self._currently_open += 1
        self.max_concurrent_open = max(self.max_concurrent_open, self._currently_open)
        sub = Subscription(
            stream_type="SymbolStatistics",
            item=f"sy{symbol}",
            on_update=on_update,
            _ls_subscription=MagicMock(),
        )
        if symbol not in self.unresponsive_symbols:
            update = self.quotes.get(symbol) or SymbolUpdate(
                {
                    "m_ShortName": symbol,
                    "m_LastTradePrice": "0",
                    "m_Change": "0",
                    "m_PercentChange": "0",
                }
            )
            on_update(update)
        return sub

    def unsubscribe(self, subscription):
        if isinstance(subscription._ls_subscription, list):
            for child in subscription._ls_subscription:
                self.unsubscribe(child)
            return
        self.unsubscribed_subs.append(subscription)
        self._currently_open -= 1


class TestGetTopMovers:
    """get_top_movers() batches through the FULL real-equity universe (from
    list_stocks(), filtered to security_class_name in LocalSecurity_IN/
    LocalSecurity_OUT/OTC) in chunks of up to `limit` concurrent
    subscriptions, capturing each symbol's snapshot and returning a sorted
    TopMover ranking covering every stock."""

    def _make_stock(
        self, stock_id: int, symbol: str, name: str, security_class_name: str = "LocalSecurity_IN"
    ) -> StockInfo:
        return StockInfo(
            stock_id=stock_id,
            symbol=symbol,
            name=name,
            market_id=1,
            security_class_name=security_class_name,
        )

    def _make_bare_client(
        self,
        stocks: list[StockInfo],
        quotes: dict[str, SymbolUpdate] | None = None,
        unresponsive_symbols: set[str] | None = None,
    ) -> Client:
        client = Client.__new__(Client)
        client._settings = MagicMock(default_market_id=1)
        client.streaming = _FakeStreamingClientForGetTopMovers(
            quotes=quotes, unresponsive_symbols=unresponsive_symbols
        )
        client.list_stocks = MagicMock(return_value=stocks)
        return client

    def _symbol_update(
        self, symbol: str, name: str, last: str, change: str, change_pct: str
    ) -> SymbolUpdate:
        return SymbolUpdate(
            {
                "m_ShortName": symbol,
                "m_StockName": name,
                "m_LastTradePrice": last,
                "m_Change": change,
                "m_PercentChange": change_pct,
            }
        )

    def test_covers_full_universe_not_just_first_limit(self):
        """Regression test: a real top mover outside the first `limit`
        entries must still appear (the SUCE bug: limit used to truncate the
        sample instead of just capping batch concurrency)."""
        stocks = [self._make_stock(i, f"SYM{i}", f"Name {i}") for i in range(12)]
        client = self._make_bare_client(stocks)

        movers = client.get_top_movers(limit=5)

        client.list_stocks.assert_called_once_with(market_id=1)
        assert len(movers) == 12
        assert {m.symbol for m in movers} == {f"SYM{i}" for i in range(12)}

    def test_market_id_override_is_forwarded(self):
        stocks = [self._make_stock(1, "AAA", "A Co")]
        client = self._make_bare_client(stocks)

        client.get_top_movers(limit=1, market_id=7)

        client.list_stocks.assert_called_once_with(market_id=7)

    def test_filters_out_non_equity_security_classes(self):
        """Tbills/bonds/futures etc. have no meaningful change_pct — only
        LocalSecurity_IN/LocalSecurity_OUT/OTC are real equities."""
        stocks = [
            self._make_stock(1, "AAA", "A Co", security_class_name="LocalSecurity_IN"),
            self._make_stock(2, "BBB", "B Co", security_class_name="LocalSecurity_OUT"),
            self._make_stock(3, "CCC", "C Co", security_class_name="OTC"),
            self._make_stock(4, "DDD", "D Bond", security_class_name="Tbills"),
            self._make_stock(5, "EEE", "E Fut", security_class_name=None),
        ]
        client = self._make_bare_client(stocks)

        movers = client.get_top_movers(limit=5)

        assert {m.symbol for m in movers} == {"AAA", "BBB", "CCC"}

    def test_returns_correctly_sorted_list(self):
        stocks = [
            self._make_stock(1, "AAA", "A Co"),
            self._make_stock(2, "BBB", "B Co"),
            self._make_stock(3, "CCC", "C Co"),
        ]
        quotes = {
            "AAA": self._symbol_update("AAA", "A Co", "10", "0.5", "1.0"),
            "BBB": self._symbol_update("BBB", "B Co", "20", "-2.0", "-5.0"),
            "CCC": self._symbol_update("CCC", "C Co", "30", "3.0", "8.0"),
        }
        client = self._make_bare_client(stocks, quotes=quotes)

        movers = client.get_top_movers(limit=3)

        assert [m.symbol for m in movers] == ["CCC", "AAA", "BBB"]
        assert movers[0].change_pct == 8.0
        assert movers[0].last == 30.0

    def test_never_exceeds_limit_concurrent_subscriptions(self):
        stocks = [self._make_stock(i, f"SYM{i}", f"Name {i}") for i in range(7)]
        client = self._make_bare_client(stocks)

        client.get_top_movers(limit=3)

        assert client.streaming.max_concurrent_open <= 3

    def test_uneven_last_batch_still_covers_all_stocks(self):
        stocks = [self._make_stock(i, f"SYM{i}", f"Name {i}") for i in range(7)]
        client = self._make_bare_client(stocks)

        movers = client.get_top_movers(limit=3)

        assert len(movers) == 7
        assert {m.symbol for m in movers} == {f"SYM{i}" for i in range(7)}

    def test_unsubscribes_all_after_returning(self):
        stocks = [self._make_stock(i, f"SYM{i}", f"Name {i}") for i in range(7)]
        client = self._make_bare_client(stocks)

        client.get_top_movers(limit=3)

        assert len(client.streaming.unsubscribed_subs) == 7
        assert set(client.streaming.subscribed_symbols) == {f"SYM{i}" for i in range(7)}

    def test_timeout_in_one_batch_does_not_block_later_batches(self):
        stocks = [self._make_stock(i, f"SYM{i}", f"Name {i}") for i in range(6)]
        client = self._make_bare_client(stocks, unresponsive_symbols={"SYM2"})

        t0 = time.monotonic()
        movers = client.get_top_movers(limit=3, timeout=0.05)
        elapsed = time.monotonic() - t0

        assert elapsed < 2.0
        # SYM2 (batch 1 laggard) is missing, but batch 2 (SYM3-5) still ran.
        assert {m.symbol for m in movers} == {"SYM0", "SYM1", "SYM3", "SYM4", "SYM5"}
        # Every stock, including the laggard, still gets unsubscribed.
        assert len(client.streaming.unsubscribed_subs) == 6
