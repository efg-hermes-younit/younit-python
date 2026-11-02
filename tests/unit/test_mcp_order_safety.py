"""Order-safety tests for the MCP server.

The server is loaded in-process with a stub client that records calls; tools
are invoked through FastMCP's ``call_tool``. No network access is used.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import conftest as conf
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from younit.mcp_server import server as mcp_server
from younit.mcp_server.safety import CAIRO_TZ, DailyOrderCounter, SafetySettings
from younit.models.orders import Order

WRITE_TOOLS = {
    "buy",
    "sell",
    "amend_order",
    "buy_fund",
    "sell_fund",
    "cancel_order",
    "cancel_fund_order",
}


class StubClient:
    """Records every call; never touches the network."""

    def __init__(self, current_order: Order | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.current_order = current_order or Order(quantity=10, price=5.0)

    def buy(self, **kwargs: Any) -> Order:
        self.calls.append(("buy", kwargs))
        return Order(quantity=kwargs["qty"], price=kwargs["limit"])

    def sell(self, **kwargs: Any) -> Order:
        self.calls.append(("sell", kwargs))
        return Order(quantity=kwargs["qty"], price=kwargs["limit"])

    def buy_fund(self, **kwargs: Any) -> Order:
        self.calls.append(("buy_fund", kwargs))
        return Order(fund_id=kwargs["fund_id"], quantity=kwargs["qty"], price=kwargs["price"])

    def sell_fund(self, **kwargs: Any) -> Order:
        self.calls.append(("sell_fund", kwargs))
        return Order(fund_id=kwargs["fund_id"], quantity=kwargs["qty"], price=kwargs["price"])

    def get_order(self, order_id: int) -> Order:
        return self.current_order

    def amend_order(self, order_id: int, **kwargs: Any) -> bool:
        self.calls.append(("amend_order", {"order_id": order_id, **kwargs}))
        return True

    def cancel_order(self, order_id: int) -> bool:
        self.calls.append(("cancel_order", {"order_id": order_id}))
        return True

    def cancel_fund_order(self, order_id: int) -> bool:
        self.calls.append(("cancel_fund_order", {"order_id": order_id}))
        return True


def _registered_tools() -> set[str]:
    return {t.name for t in asyncio.run(mcp_server.app.list_tools())}


def _call(name: str, arguments: dict[str, Any]) -> Any:
    return asyncio.run(mcp_server.app.call_tool(name, arguments))


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[StubClient]:
    """Server loaded in-process: cap of 1000 EGP, write tools enabled."""
    monkeypatch.setenv("EFG_MCP_READONLY", "false")
    monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "1000")
    monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "100")
    client = StubClient()
    monkeypatch.setattr(mcp_server, "_client", client)
    monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
    monkeypatch.setattr(mcp_server, "_order_counter", DailyOrderCounter())
    mcp_server.configure_write_tools(mcp_server._safety)
    yield client
    mcp_server._remove_write_tools()


class TestPerOrderValueCap:
    def test_buy_without_limit_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="limit price"):
            _call("buy", {"symbol": "COMI", "qty": 100000})
        assert stub.calls == []

    def test_sell_without_limit_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="limit price"):
            _call("sell", {"symbol": "COMI", "qty": 100000})
        assert stub.calls == []

    def test_buy_limit_over_cap_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="safety cap"):
            _call("buy", {"symbol": "COMI", "qty": 100, "limit": 120})
        assert stub.calls == []

    def test_sell_limit_over_cap_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="safety cap"):
            _call("sell", {"symbol": "COMI", "qty": 100, "limit": 120})
        assert stub.calls == []

    def test_buy_limit_under_cap_reaches_stub(self, stub: StubClient) -> None:
        _call("buy", {"symbol": "COMI", "qty": 100, "limit": 9.5})
        assert [name for name, _ in stub.calls] == ["buy"]
        assert stub.calls[0][1]["limit"] == 9.5

    def test_sell_limit_under_cap_reaches_stub(self, stub: StubClient) -> None:
        _call("sell", {"symbol": "COMI", "qty": 100, "limit": 9.5})
        assert [name for name, _ in stub.calls] == ["sell"]

    def test_amend_raising_value_over_cap_is_blocked(self, stub: StubClient) -> None:
        # Current order is 10 x 5.0; amending qty to 1000 makes it 5,000 EGP.
        with pytest.raises(ToolError, match="safety cap"):
            _call("amend_order", {"order_id": 1, "qty": 1000})
        assert stub.calls == []

    def test_amend_new_qty_and_price_over_cap_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="safety cap"):
            _call("amend_order", {"order_id": 1, "qty": 100, "price": 120})
        assert stub.calls == []

    def test_amend_within_cap_reaches_stub(self, stub: StubClient) -> None:
        _call("amend_order", {"order_id": 1, "qty": 20, "price": 10})
        assert [name for name, _ in stub.calls] == ["amend_order"]

    def test_amend_of_market_order_without_price_is_blocked(self, stub: StubClient) -> None:
        # A market order has no price, so the new value cannot be computed.
        stub.current_order = Order(quantity=10, price=None)
        with pytest.raises(ToolError, match="limit price"):
            _call("amend_order", {"order_id": 1, "qty": 100000})
        assert stub.calls == []

    def test_buy_fund_over_cap_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="safety cap"):
            _call("buy_fund", {"fund_id": 7, "qty": 100, "price": 120})
        assert stub.calls == []

    def test_sell_fund_over_cap_is_blocked(self, stub: StubClient) -> None:
        with pytest.raises(ToolError, match="safety cap"):
            _call("sell_fund", {"fund_id": 7, "qty": 100, "price": 120})
        assert stub.calls == []

    def test_fund_orders_under_cap_reach_stub(self, stub: StubClient) -> None:
        _call("buy_fund", {"fund_id": 7, "qty": 10, "price": 50})
        _call("sell_fund", {"fund_id": 7, "qty": 10, "price": 50})
        assert [name for name, _ in stub.calls] == ["buy_fund", "sell_fund"]

    @pytest.mark.parametrize(
        ("qty", "limit"),
        [(-100, 120.0), (100, -120.0), (0, 10.0), (100, 0.0), (100, float("nan"))],
    )
    def test_invalid_qty_or_price_is_blocked(
        self, stub: StubClient, qty: int, limit: float
    ) -> None:
        with pytest.raises(ToolError):
            _call("buy", {"symbol": "COMI", "qty": qty, "limit": limit})
        assert stub.calls == []

    def test_cancels_are_not_value_capped(self, stub: StubClient) -> None:
        _call("cancel_order", {"order_id": 1})
        _call("cancel_fund_order", {"order_id": 2})
        assert [name for name, _ in stub.calls] == ["cancel_order", "cancel_fund_order"]

    def test_disabled_cap_allows_market_order(
        self, stub: StubClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "0")
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        _call("buy", {"symbol": "COMI", "qty": 100000})
        assert [name for name, _ in stub.calls] == ["buy"]


class TestDailyOrderCap:
    def test_orders_beyond_daily_limit_are_blocked(
        self, stub: StubClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "2")
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        _call("buy", {"symbol": "COMI", "qty": 1, "limit": 10})
        _call("buy_fund", {"fund_id": 7, "qty": 1, "price": 10})
        with pytest.raises(ToolError, match="Daily order limit"):
            _call("sell", {"symbol": "COMI", "qty": 1, "limit": 10})
        assert len(stub.calls) == 2

    def test_order_blocked_by_value_cap_does_not_use_daily_quota(
        self, stub: StubClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "1")
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        with pytest.raises(ToolError, match="safety cap"):
            _call("buy", {"symbol": "COMI", "qty": 100, "limit": 120})
        with pytest.raises(ToolError, match="limit price"):
            _call("buy", {"symbol": "COMI", "qty": 100})
        assert mcp_server._order_counter.count == 0
        _call("buy", {"symbol": "COMI", "qty": 1, "limit": 10})
        assert [name for name, _ in stub.calls] == ["buy"]

    def test_order_is_counted_even_if_the_sdk_call_fails(
        self, stub: StubClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def failing_buy(**kwargs: Any) -> Order:
            raise RuntimeError("exchange unavailable")

        monkeypatch.setattr(stub, "buy", failing_buy)
        with pytest.raises(ToolError, match="exchange unavailable"):
            _call("buy", {"symbol": "COMI", "qty": 1, "limit": 10})
        assert mcp_server._order_counter.count == 1


class TestDailyOrderCounter:
    def test_concurrent_reserve_at_limit_minus_one_lets_exactly_one_through(self) -> None:
        settings = SafetySettings()
        settings.max_daily_orders = 50
        counter = DailyOrderCounter()
        for _ in range(49):
            counter.reserve(settings)

        threads = 20
        barrier = threading.Barrier(threads)

        def attempt() -> bool:
            barrier.wait()
            try:
                counter.reserve(settings)
            except ValueError:
                return False
            return True

        with ThreadPoolExecutor(max_workers=threads) as pool:
            results = list(pool.map(lambda _: attempt(), range(threads)))

        assert results.count(True) == 1
        assert counter.count == 50

    def test_blocked_reserve_does_not_count(self) -> None:
        settings = SafetySettings()
        settings.max_daily_orders = 1
        counter = DailyOrderCounter()
        counter.reserve(settings)
        with pytest.raises(ValueError, match="Daily order limit"):
            counter.reserve(settings)
        assert counter.count == 1

    def test_count_resets_at_cairo_midnight(self) -> None:
        now = [datetime(2026, 11, 2, 23, 59, tzinfo=CAIRO_TZ)]
        counter = DailyOrderCounter(clock=lambda: now[0])
        settings = SafetySettings()
        settings.max_daily_orders = 2
        counter.reserve(settings)
        counter.reserve(settings)
        with pytest.raises(ValueError, match="Daily order limit"):
            counter.reserve(settings)

        now[0] = datetime(2026, 11, 3, 0, 1, tzinfo=CAIRO_TZ)
        assert counter.count == 0
        assert counter.reserve(settings) == 1

    def test_utc_midnight_does_not_reset_the_count(self) -> None:
        # 23:59Z on Nov 2 is 01:59 in Cairo on Nov 3 (UTC+2); 00:01Z is 02:01 Cairo.
        now = [datetime(2026, 11, 2, 23, 59, tzinfo=UTC)]
        counter = DailyOrderCounter(clock=lambda: now[0])
        settings = SafetySettings()
        counter.reserve(settings)
        now[0] = datetime(2026, 11, 3, 0, 1, tzinfo=UTC)
        assert counter.count == 1

    def test_utc_evening_before_cairo_midnight_is_still_the_same_day(self) -> None:
        # 21:30Z on Nov 2 is 23:30 Cairo, still Nov 2.
        now = [datetime(2026, 11, 2, 12, 0, tzinfo=UTC)]
        counter = DailyOrderCounter(clock=lambda: now[0])
        counter.reserve(SafetySettings())
        now[0] = datetime(2026, 11, 2, 21, 30, tzinfo=UTC)
        assert counter.count == 1
        now[0] = datetime(2026, 11, 2, 22, 30, tzinfo=UTC)  # 00:30 Cairo, Nov 3
        assert counter.count == 0


class TestGetSafetySettingsTool:
    @staticmethod
    def _result(name: str = "get_safety_settings") -> dict[str, Any]:
        result = _call(name, {})
        if isinstance(result, tuple):  # (content blocks, structured content)
            result = result[1]
        if isinstance(result, dict):
            return result
        return json.loads(result[0].text)

    @pytest.fixture
    def server(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        monkeypatch.setenv("EFG_MCP_MAX_ORDER_VALUE_EGP", "250.9")
        monkeypatch.setenv("EFG_MCP_MAX_DAILY_ORDERS", "7")
        monkeypatch.setattr(mcp_server, "_order_counter", DailyOrderCounter())
        yield
        mcp_server._remove_write_tools()

    def test_returns_effective_values_in_read_only_mode(
        self, server: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EFG_MCP_READONLY", raising=False)
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        mcp_server.configure_write_tools(mcp_server._safety)
        assert _registered_tools() & WRITE_TOOLS == set()
        assert "get_safety_settings" in _registered_tools()
        assert self._result() == {
            "read_only": True,
            "max_order_value_egp": 250,
            "max_daily_orders": 7,
            "orders_sent_today": 0,
        }

    def test_reflects_trading_mode_and_orders_sent(
        self, server: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "false")
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        monkeypatch.setattr(mcp_server, "_client", StubClient())
        mcp_server.configure_write_tools(mcp_server._safety)
        _call("buy", {"symbol": "COMI", "qty": 1, "limit": 10})
        values = self._result()
        assert values["read_only"] is False
        assert values["orders_sent_today"] == 1

    def test_blocked_orders_are_not_counted(
        self, server: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "false")
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        monkeypatch.setattr(mcp_server, "_client", StubClient())
        mcp_server.configure_write_tools(mcp_server._safety)
        with pytest.raises(ToolError):
            _call("buy", {"symbol": "COMI", "qty": 100000})
        assert self._result()["orders_sent_today"] == 0

    def test_exposes_no_credentials(self, server: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADING_ID", conf.FAKE_TRADING_ID)
        monkeypatch.setenv("API_KEY", conf.FAKE_API_KEY)
        monkeypatch.setattr(mcp_server, "_safety", SafetySettings())
        values = self._result()
        assert set(values) == {
            "read_only",
            "max_order_value_egp",
            "max_daily_orders",
            "orders_sent_today",
        }
        text = json.dumps(values)
        assert conf.FAKE_TRADING_ID not in text and conf.FAKE_API_KEY not in text


class TestReadonlyDefault:
    @pytest.fixture(autouse=True)
    def _clean_tools(self) -> Iterator[None]:
        mcp_server._remove_write_tools()
        yield
        mcp_server._remove_write_tools()

    def test_unset_registers_no_write_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EFG_MCP_READONLY", raising=False)
        mcp_server.configure_write_tools(SafetySettings())
        assert _registered_tools() & WRITE_TOOLS == set()

    @pytest.mark.parametrize("value", ["", "true", "0", "no", "garbage"])
    def test_anything_but_false_registers_no_write_tools(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", value)
        mcp_server.configure_write_tools(SafetySettings())
        assert _registered_tools() & WRITE_TOOLS == set()

    def test_explicit_false_registers_write_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "false")
        mcp_server.configure_write_tools(SafetySettings())
        assert WRITE_TOOLS <= _registered_tools()

    def test_dotenv_false_registers_write_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.delenv("EFG_MCP_READONLY", raising=False)
        (tmp_path / ".env").write_text("EFG_MCP_READONLY=false\n", encoding="utf-8")
        mcp_server.configure_write_tools(SafetySettings())
        assert WRITE_TOOLS <= _registered_tools()

    @pytest.mark.parametrize("value", ["true", "0", "no", "", "garbage"])
    def test_dotenv_any_other_value_registers_no_write_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, value: str
    ) -> None:
        monkeypatch.delenv("EFG_MCP_READONLY", raising=False)
        (tmp_path / ".env").write_text(f"EFG_MCP_READONLY={value}\n", encoding="utf-8")
        mcp_server.configure_write_tools(SafetySettings())
        assert _registered_tools() & WRITE_TOOLS == set()

    def test_environment_overrides_dotenv_for_write_tools(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        (tmp_path / ".env").write_text("EFG_MCP_READONLY=false\n", encoding="utf-8")
        monkeypatch.setenv("EFG_MCP_READONLY", "true")
        mcp_server.configure_write_tools(SafetySettings())
        assert _registered_tools() & WRITE_TOOLS == set()

    def test_switching_back_to_readonly_removes_write_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EFG_MCP_READONLY", "false")
        mcp_server.configure_write_tools(SafetySettings())
        monkeypatch.delenv("EFG_MCP_READONLY")
        mcp_server.configure_write_tools(SafetySettings())
        assert _registered_tools() & WRITE_TOOLS == set()
