"""Unit tests for MCP server safety controls."""

from __future__ import annotations

import pytest

from younit.mcp_server.safety import (
    DailyOrderCounter,
    SafetySettings,
    check_daily_limit,
    check_order_value,
)


class TestSafetySettings:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EFG_MCP_READONLY", raising=False)
        monkeypatch.delenv("EFG_MCP_MAX_ORDER_VALUE_EGP", raising=False)
        monkeypatch.delenv("EFG_MCP_MAX_DAILY_ORDERS", raising=False)
        settings = SafetySettings()
        assert settings.readonly is False
        assert settings.max_order_value_egp == 1_000
        assert settings.max_daily_orders == 100

    def test_readonly_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "true")
        settings = SafetySettings()
        assert settings.readonly is True

    def test_readonly_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "false")
        settings = SafetySettings()
        assert settings.readonly is False

    def test_custom_order_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "50000")
        settings = SafetySettings()
        assert settings.max_order_value_egp == 50_000

    def test_custom_daily_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "10")
        settings = SafetySettings()
        assert settings.max_daily_orders == 10


class TestCheckOrderValue:
    def test_within_cap_passes(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 100_000
        check_order_value(100, 500.0, settings)  # 50,000 EGP < 100,000

    def test_exceeds_cap_raises(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 50_000
        with pytest.raises(ValueError, match="safety cap"):
            check_order_value(1000, 100.0, settings)  # 100,000 > 50,000

    def test_market_order_skips_check(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 1  # tiny cap
        check_order_value(1000000, None, settings)  # market order, no price

    def test_disabled_cap_passes_anything(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 0  # disabled
        check_order_value(1000000, 10000.0, settings)

    def test_exactly_at_cap_passes(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 100_000
        check_order_value(1000, 100.0, settings)  # exactly 100,000


class TestCheckDailyLimit:
    def test_under_limit_passes(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_daily_orders = 5
        counter = DailyOrderCounter()
        check_daily_limit(counter, settings)  # 0 orders, limit is 5

    def test_at_limit_raises(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_daily_orders = 2
        counter = DailyOrderCounter()
        counter.increment()
        counter.increment()
        with pytest.raises(ValueError, match="Daily order limit"):
            check_daily_limit(counter, settings)

    def test_disabled_limit_passes_anything(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_daily_orders = 0  # disabled
        counter = DailyOrderCounter()
        for _ in range(1000):
            counter.increment()
        check_daily_limit(counter, settings)  # Should not raise


class TestDailyOrderCounter:
    def test_starts_at_zero(self) -> None:
        counter = DailyOrderCounter()
        assert counter.count == 0

    def test_increment_increases_count(self) -> None:
        counter = DailyOrderCounter()
        counter.increment()
        counter.increment()
        assert counter.count == 2

    def test_increment_returns_new_count(self) -> None:
        counter = DailyOrderCounter()
        assert counter.increment() == 1
        assert counter.increment() == 2
