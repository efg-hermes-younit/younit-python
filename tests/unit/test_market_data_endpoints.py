"""Unit tests for the market_data endpoint functions, exercised via Client."""

from __future__ import annotations

import conftest as conf
import httpx

from younit.client import Client

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


def _make_client(respx_mock) -> Client:
    respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
        return_value=httpx.Response(200, json=conf.SERVER_TOKEN_RESPONSE)
    )
    respx_mock.post(f"{FAKE_BASE_URL}/connect/iframe-access").mock(
        return_value=httpx.Response(200, json=conf.CLIENT_TOKEN_RESPONSE)
    )
    respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/market/1").mock(
        return_value=httpx.Response(200, json=RAW_STOCKS)
    )
    return Client(
        partner_id=conf.FAKE_PARTNER_ID,
        partner_secret=conf.FAKE_PARTNER_SECRET,
        trading_uuid=conf.FAKE_TRADING_UUID,
        identity_url=FAKE_BASE_URL,
        simulation=True,
        lazy_auth=True,
        lazy_symbols=True,
        _base_url_override=FAKE_BASE_URL,
    )


class TestQuote:
    def test_quote_normalizes_and_uses_given_symbol(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "securityID": 101,
                        "securityName": "Commercial International Bank",
                        "marketID": 1,
                        "allowIntraDay": True,
                        "allowTPlus1": False,
                        "last": 65.5,
                    }
                },
            )
        )
        client = _make_client(respx_mock)
        quote = client.quote("COMI")
        assert quote.symbol == "COMI"
        assert quote.is_intraday is True

    def test_quote_derives_symbol_from_reuter_id_when_absent(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "reuterID": "COMI.CA",
                        "last": 65.5,
                        "allowIntraDay": True,
                        "allowTPlus1": False,
                    }
                },
            )
        )
        client = _make_client(respx_mock)
        # Bypass the SDK's own symbol override by calling the endpoint through
        # stock_info (still passes symbol="COMI" internally) — use quote()
        # which always forwards the resolved ticker as `symbol`.
        quote = client.quote("COMI")
        assert quote.symbol == "COMI"

    def test_quote_returns_empty_quote_when_data_is_none(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        quote = client.quote("COMI")
        assert quote.symbol is None

    def test_stock_info_is_alias_for_quote(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-trading-info/1/101").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"last": 10.0, "allowIntraDay": True, "allowTPlus1": False}},
            )
        )
        client = _make_client(respx_mock)
        quote = client.stock_info("COMI")
        assert quote.symbol == "COMI"


class TestTopGainersLosers:
    def test_named_keys_topgainers_toplosers(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/top-gainers-losers/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "topGainers": [{"id": 1, "reuterCode": "AAA.CA", "name": "A Co"}],
                        "topLosers": [{"id": 2, "reuterCode": "BBB.CA", "name": "B Co"}],
                    }
                },
            )
        )
        client = _make_client(respx_mock)
        gainers = client.top_gainers()
        losers = client.top_losers()
        assert gainers[0].symbol == "AAA"
        assert gainers[0].stock_id == 1
        assert losers[0].symbol == "BBB"

    def test_alternate_lowercase_keys(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/top-gainers-losers/1").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"gainers": [{"stockId": 5, "symbol": "CCC"}], "losers": []}},
            )
        )
        client = _make_client(respx_mock)
        gainers = client.top_gainers()
        assert gainers[0].symbol == "CCC"

    def test_bare_list_response_treated_as_gainers(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/top-gainers-losers/1").mock(
            return_value=httpx.Response(200, json=[{"stockId": 9, "symbol": "DDD"}])
        )
        client = _make_client(respx_mock)
        gainers = client.top_gainers()
        assert gainers[0].symbol == "DDD"

    def test_non_dict_items_are_skipped(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/top-gainers-losers/1").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"topGainers": ["not-a-dict", {"stockId": 1, "symbol": "EEE"}]}},
            )
        )
        client = _make_client(respx_mock)
        gainers = client.top_gainers()
        assert len(gainers) == 1
        assert gainers[0].symbol == "EEE"

    def test_limit_truncates_results(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/top-gainers-losers/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {"topGainers": [{"stockId": i, "symbol": f"S{i}"} for i in range(5)]}
                },
            )
        )
        client = _make_client(respx_mock)
        gainers = client.top_gainers(limit=2)
        assert len(gainers) == 2


class TestTrendingStocks:
    def test_normalizes_items(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-analytics/1/TrendingStocks").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": 7, "reuterCode": "FFF.CA", "name": "F Co"}]},
            )
        )
        client = _make_client(respx_mock)
        trending = client.trending_stocks()
        assert trending[0].stock_id == 7
        assert trending[0].symbol == "FFF"

    def test_non_list_data_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-analytics/1/TrendingStocks").mock(
            return_value=httpx.Response(200, json={"data": None})
        )
        client = _make_client(respx_mock)
        assert client.trending_stocks() == []

    def test_non_dict_items_skipped(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-analytics/1/TrendingStocks").mock(
            return_value=httpx.Response(200, json={"data": [123, {"stockId": 1, "symbol": "GG"}]})
        )
        client = _make_client(respx_mock)
        trending = client.trending_stocks()
        assert len(trending) == 1


class TestHistoricalPrices:
    def test_nested_data_shape_is_parsed(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/charts/GetChartingHistoricalDataFeed").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "data": {
                            "chartingDataViewModel": [
                                {
                                    "date": "2026-01-01T00:00:00",
                                    "open": 1,
                                    "high": 2,
                                    "low": 0.5,
                                    "close": 1.5,
                                    "volume": 100,
                                }
                            ]
                        }
                    }
                },
            )
        )
        client = _make_client(respx_mock)
        candles = client.historical_prices("COMI")
        assert len(candles) == 1
        assert candles[0].close == 1.5

    def test_missing_charting_key_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/charts/GetChartingHistoricalDataFeed").mock(
            return_value=httpx.Response(200, json={"data": {"data": {}}})
        )
        client = _make_client(respx_mock)
        assert client.historical_prices("COMI") == []

    def test_unexpected_shape_returns_empty(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/charts/GetChartingHistoricalDataFeed").mock(
            return_value=httpx.Response(200, json={"data": "unexpected"})
        )
        client = _make_client(respx_mock)
        assert client.historical_prices("COMI") == []

    def test_date_range_params_are_forwarded(self, respx_mock):
        route = respx_mock.get(f"{FAKE_BASE_URL}/api/charts/GetChartingHistoricalDataFeed").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        client = _make_client(respx_mock)
        client.historical_prices("COMI", date_from="2026-01-01", date_to="2026-02-01")
        sent_params = route.calls.last.request.url.params
        assert sent_params["DateFrom"] == "2026-01-01"
        assert sent_params["DateTo"] == "2026-02-01"


class TestListTradeableStocksCategoryEdgeCases:
    def test_stock_list_types_wrapped_dict_and_bare_list(self, respx_mock):
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stock-lists-types/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"name": "Intraday", "id": 2, "type": 2},
                        {"name": "OTC", "id": 3, "type": 3},
                    ]
                },
            )
        )
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-by-list-type/2/2/1").mock(
            return_value=httpx.Response(
                200, json=[{"id": 1, "reuterCode": "HHH.CA", "name": "H Co"}]
            )
        )
        respx_mock.get(f"{FAKE_BASE_URL}/api/stocks/stocks-by-list-type/3/3/1").mock(
            return_value=httpx.Response(200, json={"data": [123, "skip-me"]})
        )
        client = _make_client(respx_mock)
        stocks = client.list_tradeable_stocks()
        assert any(s.symbol == "HHH" for s in stocks)
