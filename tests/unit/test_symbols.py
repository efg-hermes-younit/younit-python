"""Unit tests for the symbol cache."""

from __future__ import annotations

import pytest

from younit.exceptions import InvalidSymbol
from younit.symbols import SymbolCache

SAMPLE_STOCKS = [
    {"stockId": 1001, "symbol": "COMI", "stockName": "Commercial International Bank"},
    {"stockId": 1002, "symbol": "HRHO", "stockName": "EFG Hermes Holding"},
    {"stockId": 1003, "symbol": "ETEL", "stockName": "Telecom Egypt"},
    {"stockId": 1004, "symbol": "MNHD", "stockName": "Medinet Nasr for Housing"},
]


class TestSymbolCache:
    def test_not_loaded_initially(self) -> None:
        cache = SymbolCache()
        assert not cache.is_loaded

    def test_load_populates_cache(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        assert cache.is_loaded

    def test_resolve_success(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        assert cache.resolve("COMI") == 1001
        assert cache.resolve("HRHO") == 1002

    def test_resolve_case_insensitive(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        assert cache.resolve("comi") == 1001
        assert cache.resolve("Comi") == 1001

    def test_resolve_unknown_raises(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        with pytest.raises(InvalidSymbol) as exc_info:
            cache.resolve("FAKE")
        assert exc_info.value.symbol == "FAKE"
        assert exc_info.value.market_id == 1

    def test_resolve_not_loaded_raises(self) -> None:
        cache = SymbolCache()
        with pytest.raises(RuntimeError, match="not loaded"):
            cache.resolve("COMI")

    def test_lookup_by_stock_id(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        assert cache.lookup(1001) == "COMI"
        assert cache.lookup(9999) is None

    def test_search(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        results = cache.search("COM")
        symbols = [sym for sym, _ in results]
        assert "COMI" in symbols

    def test_search_no_results(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        results = cache.search("ZZZZ")
        assert results == []

    def test_all_symbols(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        symbols = cache.all_symbols()
        assert "COMI" in symbols
        assert "HRHO" in symbols
        assert len(symbols) == 4

    def test_reload_replaces_cache(self) -> None:
        cache = SymbolCache()
        cache.load(SAMPLE_STOCKS)
        assert cache.resolve("COMI") == 1001

        # Reload with different data
        cache.load([{"stockId": 2001, "symbol": "NEWSTOCK", "stockName": "New Corp"}])
        with pytest.raises(InvalidSymbol):
            cache.resolve("COMI")
        assert cache.resolve("NEWSTOCK") == 2001
