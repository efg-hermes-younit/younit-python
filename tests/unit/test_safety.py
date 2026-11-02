"""Unit tests for MCP server safety controls."""

from __future__ import annotations

import os
import pathlib

import conftest as conf
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
        assert settings.readonly is True
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

    @pytest.mark.parametrize("value", ["", "0", "no", "garbage"])
    def test_readonly_only_disabled_by_explicit_false(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", value)
        assert SafetySettings().readonly is True

    def test_custom_order_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "50000")
        settings = SafetySettings()
        assert settings.max_order_value_egp == 50_000

    def test_custom_daily_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "10")
        settings = SafetySettings()
        assert settings.max_daily_orders == 10


class TestSafetySettingsDotenv:
    """EFG_MCP_* settings come from the environment first, then .env in the cwd."""

    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "EFG_MCP_READONLY",
            "EFG_MCP_MAX_ORDER_VALUE_EGP",
            "EFG_MCP_MAX_DAILY_ORDERS",
        ):
            monkeypatch.delenv(name, raising=False)

    @staticmethod
    def _write_env(tmp_path: pathlib.Path, text: str) -> None:
        (tmp_path / ".env").write_text(text, encoding="utf-8")

    def test_values_from_dotenv_apply(self, tmp_path: pathlib.Path) -> None:
        self._write_env(
            tmp_path,
            "EFG_MCP_READONLY=false\nEFG_MCP_MAX_ORDER_VALUE_EGP=2500\nEFG_MCP_MAX_DAILY_ORDERS=7\n",
        )
        settings = SafetySettings()
        assert settings.readonly is False
        assert settings.max_order_value_egp == 2_500
        assert settings.max_daily_orders == 7

    def test_zero_in_dotenv_disables_limits(self, tmp_path: pathlib.Path) -> None:
        self._write_env(tmp_path, "EFG_MCP_MAX_ORDER_VALUE_EGP=0\nEFG_MCP_MAX_DAILY_ORDERS=0\n")
        settings = SafetySettings()
        assert settings.max_order_value_egp == 0
        assert settings.max_daily_orders == 0

    def test_environment_overrides_dotenv(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_env(
            tmp_path,
            "EFG_MCP_READONLY=false\nEFG_MCP_MAX_ORDER_VALUE_EGP=2500\nEFG_MCP_MAX_DAILY_ORDERS=7\n",
        )
        monkeypatch.setenv("EFG_MCP_READONLY", "true")
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "300")
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "3")
        settings = SafetySettings()
        assert settings.readonly is True
        assert settings.max_order_value_egp == 300
        assert settings.max_daily_orders == 3

    def test_dotenv_is_not_loaded_into_os_environ(self, tmp_path: pathlib.Path) -> None:
        self._write_env(tmp_path, "EFG_MCP_READONLY=false\n")
        SafetySettings()
        assert "EFG_MCP_READONLY" not in os.environ

    def test_missing_dotenv_gives_safe_defaults(self) -> None:
        settings = SafetySettings()
        assert settings.readonly is True
        assert settings.max_order_value_egp == 1_000
        assert settings.max_daily_orders == 100

    def test_unrelated_dotenv_keys_are_ignored(self, tmp_path: pathlib.Path) -> None:
        self._write_env(
            tmp_path, f"TRADING_ID={conf.FAKE_TRADING_ID}\nAPI_KEY={conf.FAKE_API_KEY}\n"
        )
        assert SafetySettings().readonly is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "False", " false "])
    def test_dotenv_false_enables_write_tools(self, tmp_path: pathlib.Path, value: str) -> None:
        self._write_env(tmp_path, f'EFG_MCP_READONLY="{value}"\n')
        assert SafetySettings().readonly is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "0", "no", "off", "", "falsee", "garbage"])
    def test_dotenv_any_other_value_stays_readonly(
        self, tmp_path: pathlib.Path, value: str
    ) -> None:
        self._write_env(tmp_path, f"EFG_MCP_READONLY={value}\n")
        assert SafetySettings().readonly is True

    @pytest.mark.parametrize(
        "value",
        [
            "abc",
            "-5",
            "-5.5",
            "",
            "  ",
            "1e3",
            "ten",
            "0.5",
            "0.99",
            "250.",
            ".5",
            "+5",
            "nan",
            "inf",
        ],
    )
    def test_invalid_limits_in_dotenv_fall_back_to_defaults(
        self, tmp_path: pathlib.Path, value: str
    ) -> None:
        self._write_env(
            tmp_path,
            f"EFG_MCP_MAX_ORDER_VALUE_EGP={value}\nEFG_MCP_MAX_DAILY_ORDERS={value}\n",
        )
        settings = SafetySettings()
        assert settings.max_order_value_egp == 1_000
        assert settings.max_daily_orders == 100

    @pytest.mark.parametrize("value", ["abc", "-1", "-5", "0.5"])
    def test_invalid_limits_in_environment_fall_back_to_defaults(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", value)
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", value)
        settings = SafetySettings()
        assert settings.max_order_value_egp == 1_000
        assert settings.max_daily_orders == 100

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("250", 250),
            (" 250 ", 250),
            ("250.0", 250),
            ("250.9", 250),
            ("3.7", 3),
            ("1.5", 1),
            ("0", 0),
            ("0.0", 0),
            ("007", 7),
        ],
    )
    def test_whole_and_fractional_limits_round_down(
        self, monkeypatch: pytest.MonkeyPatch, value: str, expected: int
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", value)
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", value)
        settings = SafetySettings()
        assert settings.max_order_value_egp == expected
        assert settings.max_daily_orders == expected

    def test_fractional_limits_from_dotenv_round_down(self, tmp_path: pathlib.Path) -> None:
        self._write_env(
            tmp_path, 'EFG_MCP_MAX_ORDER_VALUE_EGP="250.9"\nEFG_MCP_MAX_DAILY_ORDERS=3.7\n'
        )
        settings = SafetySettings()
        assert settings.max_order_value_egp == 250
        assert settings.max_daily_orders == 3

    def test_unreadable_dotenv_fails_safe(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".env").write_bytes(b"EFG_MCP_READONLY=false\n\xff\xfe\x00\x80\n")
        settings = SafetySettings()
        assert settings.readonly is True
        assert settings.max_order_value_egp == 1_000
        assert settings.max_daily_orders == 100


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

    def test_market_order_rejected_while_cap_active(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 1  # tiny cap
        with pytest.raises(ValueError, match="limit price"):
            check_order_value(1000000, None, settings)

    def test_market_order_allowed_when_cap_disabled(self) -> None:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 0
        check_order_value(1000000, None, settings)

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
