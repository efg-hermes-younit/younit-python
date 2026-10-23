"""Unit tests for the funds endpoint functions, exercised via Client."""

from __future__ import annotations

import conftest as conf
import httpx
import pytest

from younit.client import Client
from younit.exceptions import InvalidOrder, NotFound

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


class TestListFunds:
    def test_wrapped_data_list_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"securityID": 10, "securityName": "Money Market Fund"}]},
            )
        )
        client = _make_client(respx_mock)
        funds = client.list_funds()
        assert len(funds) == 1
        assert funds[0].fund_id == 10
        assert funds[0].name == "Money Market Fund"

    def test_bare_list_response_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(200, json=[{"securityID": 11, "securityName": "Fund B"}])
        )
        client = _make_client(respx_mock)
        funds = client.list_funds()
        assert len(funds) == 1
        assert funds[0].fund_id == 11

    def test_non_list_response_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        assert client.list_funds() == []


class TestGetFund:
    def test_found_fund_returned(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(
                200, json={"data": [{"securityID": 10, "securityName": "Fund A"}]}
            )
        )
        client = _make_client(respx_mock)
        fund = client.fund(10)
        assert fund.fund_id == 10

    def test_missing_fund_raises_not_found(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/1").mock(
            return_value=httpx.Response(
                200, json={"data": [{"securityID": 10, "securityName": "Fund A"}]}
            )
        )
        client = _make_client(respx_mock)
        with pytest.raises(NotFound):
            client.fund(999)


class TestFundPerformance:
    def test_chart_data_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/PerformanceChart/1/10/3").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"date": "2026-01-01T00:00:00", "price": 1.5}]},
            )
        )
        client = _make_client(respx_mock)
        perf = client.fund_performance(10)
        assert perf.fund_id == 10
        assert len(perf.chart_data) == 1
        assert perf.chart_data[0].value == 1.5

    def test_empty_data_returns_default_performance(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/PerformanceChart/1/10/3").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        client = _make_client(respx_mock)
        perf = client.fund_performance(10)
        assert perf.fund_id == 10
        assert perf.chart_data == []

    def test_non_list_data_returns_default_performance(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/PerformanceChart/1/10/3").mock(
            return_value=httpx.Response(200, json={"data": {"unexpected": "shape"}})
        )
        client = _make_client(respx_mock)
        perf = client.fund_performance(10)
        assert perf.chart_data == []


class TestFundOrderHistory:
    def test_raises_without_resolvable_profile_id(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/market/1").mock(
            return_value=httpx.Response(200, json=[])
        )
        client = _make_client(respx_mock)
        with pytest.raises(InvalidOrder):
            client.fund_order_history()

    def test_rows_parsed_and_non_dict_rows_skipped(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/order-history/1/555").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"orderID": 1, "securityId": 10, "quantity": 5},
                        "not-a-dict-row",
                    ]
                },
            )
        )
        client = _make_client(respx_mock)
        history = client.fund_order_history(profile_id=555)
        assert len(history) == 1
        assert history[0].order_id == 1

    def test_non_list_data_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/Funds/order-history/1/555").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        assert client.fund_order_history(profile_id=555) == []
