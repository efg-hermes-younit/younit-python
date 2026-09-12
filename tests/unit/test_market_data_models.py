"""Unit tests for younit.models.market_data."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from younit.models.market_data import HistoricalCandle

_CAIRO_TZ = ZoneInfo("Africa/Cairo")


class TestHistoricalCandleTimestamp:
    def test_parses_naive_iso_string_as_cairo_local_time(self) -> None:
        candle = HistoricalCandle(dateTime="2026-08-26T00:00:00")

        assert candle.timestamp == datetime(2026, 8, 26, 0, 0, 0, tzinfo=_CAIRO_TZ)
        assert candle.timestamp.tzinfo is not None

    def test_invalid_string_returns_none(self) -> None:
        candle = HistoricalCandle(dateTime="not-a-date")

        assert candle.timestamp is None

    def test_none_stays_none(self) -> None:
        candle = HistoricalCandle(dateTime=None)

        assert candle.timestamp is None


class TestHistoricalCandlePrintTable:
    def test_print_table_runs_without_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        candles = [
            HistoricalCandle(
                dateTime="2026-08-01",
                openPrice=10.0,
                highPrice=12.5,
                lowPrice=9.5,
                price=11.25,
                volume=1500,
            ),
            HistoricalCandle(
                dateTime="2026-08-02",
                openPrice=11.25,
                highPrice=13.0,
                lowPrice=11.0,
                price=12.75,
                volume=2300,
            ),
            HistoricalCandle(
                dateTime="2026-08-03",
                openPrice=12.75,
                highPrice=12.75,
                lowPrice=10.5,
                price=10.9,
                volume=980,
            ),
        ]

        HistoricalCandle.print_table(candles)

        out = capsys.readouterr().out
        assert "Date" in out
        assert "Open" in out
        assert "High" in out
        assert "Low" in out
        assert "Close" in out
        assert "Volume" in out
        assert "2026-08-01" in out
        assert "11.25" in out
