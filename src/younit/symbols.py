"""Ticker ↔ stockID symbol resolution cache.

The trading API uses integer ``stockId`` values in all trading endpoints.
End users work with human-readable ticker strings like ``"COMI"`` or ``"HRHO"``.

This module builds and maintains a mapping from uppercase ticker symbols to
their integer stockId, using the ``GET /api/stocks/market/{marketId}`` endpoint.

The cache is per-Client (not global) and lives for the Client's lifetime.
Call :meth:`SymbolCache.refresh` to rebuild from the API.
"""

from __future__ import annotations

from typing import Any

from younit.exceptions import InvalidSymbol
from younit.logging import get_logger

_log = get_logger(__name__)


class SymbolCache:
    """Maintains a ticker→stockId lookup table for a single market.

    Built from ``GET /api/stocks/market/{marketId}``, which returns the
    complete list of stocks with their ``stockId`` and ``symbol`` fields.

    Args:
        market_id: The market to cache symbols for (default 1 = EGX).
    """

    def __init__(self, market_id: int = 1) -> None:
        self._market_id = market_id
        self._symbol_to_id: dict[str, int] = {}
        self._id_to_symbol: dict[int, str] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Return True if the cache has been populated."""
        return self._loaded

    def load(self, stocks: list[dict[str, Any]]) -> None:
        """Populate the cache from a list of stock dicts returned by the API.

        Args:
            stocks: List of stock objects from ``GET /api/stocks/market/{marketId}``.
                Each object must have ``stockId`` (int) and ``symbol`` (str) fields.
        """
        new_map: dict[str, int] = {}
        new_reverse: dict[int, str] = {}

        for stock in stocks:
            stock_id = stock.get("stockId") or stock.get("id")
            symbol = stock.get("symbol") or stock.get("Symbol")
            if not symbol:
                # API returns reuterCode like "COMI.CA"; strip the exchange suffix
                reuter = stock.get("reuterCode") or ""
                symbol = reuter.split(".")[0] if reuter else None
            if stock_id is not None and symbol:
                key = str(symbol).upper()
                new_map[key] = int(stock_id)
                new_reverse[int(stock_id)] = key

        self._symbol_to_id = new_map
        self._id_to_symbol = new_reverse
        self._loaded = True
        _log.info(
            "symbol_cache_loaded",
            market_id=self._market_id,
            symbol_count=len(new_map),
        )

    def resolve(self, symbol: str) -> int:
        """Resolve a ticker string to its integer stockId.

        Args:
            symbol: Ticker string (case-insensitive, e.g. ``"COMI"`` or ``"comi"``).

        Returns:
            The integer stockId for the symbol.

        Raises:
            InvalidSymbol: If the symbol is not found in the cache.
            RuntimeError: If the cache has not been loaded yet.
        """
        if not self._loaded:
            raise RuntimeError(
                "Symbol cache is not loaded. This is an internal error — "
                "the Client should have loaded it on init."
            )
        key = symbol.upper()
        stock_id = self._symbol_to_id.get(key)
        if stock_id is None:
            raise InvalidSymbol(symbol, self._market_id)
        return stock_id

    def lookup(self, stock_id: int) -> str | None:
        """Look up the ticker symbol for a given stockId.

        Args:
            stock_id: Integer stockId to look up.

        Returns:
            The ticker string, or None if not found.
        """
        return self._id_to_symbol.get(stock_id)

    def search(self, query: str) -> list[tuple[str, int]]:
        """Search for symbols whose ticker or name contains the query string.

        This is a local search over the cached symbol map (case-insensitive).

        Args:
            query: Search string to match against ticker symbols.

        Returns:
            List of ``(symbol, stock_id)`` tuples matching the query.
        """
        q = query.upper()
        return [(sym, sid) for sym, sid in self._symbol_to_id.items() if q in sym]

    def all_symbols(self) -> list[str]:
        """Return all cached ticker symbols."""
        return sorted(self._symbol_to_id.keys())
