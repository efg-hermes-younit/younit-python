"""Unit tests for the account/portfolio endpoint functions, exercised via Client."""

from __future__ import annotations

import conftest as conf
import httpx

from younit.client import Client

FAKE_BASE_URL = conf.FAKE_BASE_URL


def _make_client(respx_mock) -> Client:
    respx_mock.post(conf.TOKEN_URL).mock(
        return_value=httpx.Response(200, json=conf.CLIENT_TOKEN_RESPONSE)
    )
    return Client(
        trading_id=conf.FAKE_TRADING_ID,
        api_key=conf.FAKE_API_KEY,
        simulation=True,
        lazy_auth=True,
        lazy_symbols=True,
        _base_url_override=FAKE_BASE_URL,
    )


class TestAccountInfo:
    def test_wrapped_data_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").mock(
            return_value=httpx.Response(200, json={"data": {"clientName": "Jane Doe"}})
        )
        client = _make_client(respx_mock)
        info = client.account_info()
        assert info.client_name == "Jane Doe"

    def test_null_data_returns_default_account_info(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/account-utils/GetAccountInfo").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        info = client.account_info()
        assert info.client_name is None


class TestPortfolioSummary:
    def test_wrapped_data_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSummary").mock(
            return_value=httpx.Response(200, json={"data": {"totalCash": 1000.0}})
        )
        client = _make_client(respx_mock)
        summary = client.portfolio()
        assert summary.total_cash == 1000.0

    def test_null_data_returns_default_summary(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSummary").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        summary = client.portfolio()
        assert summary.total_cash == 0.0


class TestStockPositions:
    def test_stocks_list_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"stocks": [{"securityID": 10, "quantity": 5}]}},
            )
        )
        client = _make_client(respx_mock)
        positions = client.positions()
        assert len(positions) == 1
        assert positions[0].stock_id == 10

    def test_null_data_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        assert client.positions() == []

    def test_missing_stocks_key_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json={"data": {"stocksValue": 0}})
        )
        client = _make_client(respx_mock)
        assert client.positions() == []

    def test_non_list_stocks_value_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetStocksPortfolio").mock(
            return_value=httpx.Response(200, json={"data": {"stocks": "not-a-list"}})
        )
        client = _make_client(respx_mock)
        assert client.positions() == []


class TestFundPositions:
    def test_fund_rows_filtered_by_is_fund_flag(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "securityPositions": [
                            {"securityID": 1, "isFund": False},
                            {"securityID": 2, "isFund": True},
                        ]
                    }
                },
            )
        )
        client = _make_client(respx_mock)
        funds = client.fund_positions()
        assert len(funds) == 1
        assert funds[0].fund_id == 2

    def test_null_data_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        assert client.fund_positions() == []

    def test_non_list_security_positions_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/portfolio/GetPortfolioSecurities").mock(
            return_value=httpx.Response(200, json={"data": {"securityPositions": "not-a-list"}})
        )
        client = _make_client(respx_mock)
        assert client.fund_positions() == []
