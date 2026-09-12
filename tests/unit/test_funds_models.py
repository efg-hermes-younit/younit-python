"""Unit tests for younit.models.funds."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from younit.models.funds import Fund, FundOrderHistoryEntry, PerformanceDataPoint

_CAIRO_TZ = ZoneInfo("Africa/Cairo")


class TestPerformanceDataPointDate:
    def test_parses_utc_z_string_to_cairo_local_time(self) -> None:
        dp = PerformanceDataPoint(date="2026-01-27T22:00:00Z")

        # 22:00 UTC == 00:00 Cairo (UTC+2) the next day.
        assert dp.date == datetime(2026, 1, 28, 0, 0, 0, tzinfo=_CAIRO_TZ)
        assert dp.date.tzinfo is not None

    def test_invalid_string_returns_none(self) -> None:
        dp = PerformanceDataPoint(date="not-a-date")

        assert dp.date is None

    def test_none_stays_none(self) -> None:
        dp = PerformanceDataPoint(date=None)

        assert dp.date is None


class TestFundLaunchDate:
    def test_parses_utc_z_string_to_cairo_local_time(self) -> None:
        fund = Fund(launchDate="2026-01-28T07:00:00Z")

        # 07:00 UTC == 09:00 Cairo (UTC+2).
        assert fund.launch_date == datetime(2026, 1, 28, 9, 0, 0, tzinfo=_CAIRO_TZ)
        assert fund.launch_date.tzinfo is not None

    def test_invalid_string_returns_none(self) -> None:
        fund = Fund(launchDate="not-a-date")

        assert fund.launch_date is None


class TestFundCutOffTime:
    def test_parses_12h_am_pm_string_as_cairo_local_time(self) -> None:
        fund = Fund(cutOffTime="09:00 AM")

        assert fund.cut_off_time == time(9, 0, tzinfo=_CAIRO_TZ)
        assert fund.cut_off_time.tzinfo is not None

    def test_invalid_string_returns_none(self) -> None:
        fund = Fund(cutOffTime="not-a-time")

        assert fund.cut_off_time is None


class TestFundOrderHistoryEntryOrderDate:
    def test_parses_real_captured_mm_dd_yyyy_sample(self) -> None:
        entry = FundOrderHistoryEntry(orderDate="09/07/2026 12:39:54")

        assert entry.order_date == datetime(2026, 9, 7, 12, 39, 54)

    def test_invalid_string_returns_none(self) -> None:
        entry = FundOrderHistoryEntry(orderDate="not-a-date")

        assert entry.order_date is None

    def test_none_stays_none(self) -> None:
        entry = FundOrderHistoryEntry(orderDate=None)

        assert entry.order_date is None


class TestFundPrintTable:
    def test_print_table_runs_without_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        funds = [
            Fund(
                securityID=101,
                securityName="EFG Hermes Gold Fund",
                fundType="Commodities",
                price=12.3456,
                priceChangePercentage=1.25,
                currencyShortName="EGP",
                isUserSubscribed=True,
            ),
            Fund(
                securityID=102,
                securityName="EFG Hermes Money Market Fund",
                fundType="Money Market",
                price=100.0,
                priceChangePercentage=-0.5,
                currencyShortName="EGP",
                isUserSubscribed=False,
            ),
        ]

        Fund.print_table(funds)

        out = capsys.readouterr().out
        assert "Name" in out
        assert "NAV" in out
        assert "EFG Hermes Gold Fund" in out
        assert "12.3456" in out
        assert "True" in out
        assert "False" in out
