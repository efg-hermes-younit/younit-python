"""Unit tests for MCP server tool handlers (src/younit/mcp_server/server.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from younit.mcp_server import server as mcp_server
from younit.mcp_server.safety import SafetySettings
from younit.models.market_data import StockInfo
from younit.models.orders import Order
from younit.models.portfolio import FundPosition, Position
from younit.models.streaming import TopMover


def _sell_fn():
    mcp_server._register_write_tools()
    tool = mcp_server.app._tool_manager.get_tool("sell")
    assert tool is not None
    return tool.fn


def _buy_fund_fn():
    mcp_server._register_write_tools()
    tool = mcp_server.app._tool_manager.get_tool("buy_fund")
    assert tool is not None
    return tool.fn


def _sell_fund_fn():
    mcp_server._register_write_tools()
    tool = mcp_server.app._tool_manager.get_tool("sell_fund")
    assert tool is not None
    return tool.fn


def _cancel_fund_order_fn():
    mcp_server._register_write_tools()
    tool = mcp_server.app._tool_manager.get_tool("cancel_fund_order")
    assert tool is not None
    return tool.fn


def _no_cap_safety() -> SafetySettings:
    settings = SafetySettings.__new__(SafetySettings)
    settings.max_order_value_egp = 0
    settings.max_daily_orders = 0
    return settings


def _amend_order_fn():
    mcp_server._register_write_tools()
    tool = mcp_server.app._tool_manager.get_tool("amend_order")
    assert tool is not None
    return tool.fn


class TestTopMoversTool:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client

    def test_top_gainers_and_top_losers_are_not_registered(self) -> None:
        # Confirmed unreliable REST endpoints — replaced entirely by top_movers,
        # not left registered alongside it.
        assert mcp_server.app._tool_manager.get_tool("top_gainers") is None
        assert mcp_server.app._tool_manager.get_tool("top_losers") is None

    def test_top_movers_is_registered(self) -> None:
        tool = mcp_server.app._tool_manager.get_tool("top_movers")
        assert tool is not None

    def test_top_movers_wraps_client_get_top_movers_and_serializes_dataclasses(self) -> None:
        mock_client = MagicMock()
        mock_client.get_top_movers.return_value = [
            TopMover(
                stock_id=1, symbol="COMI", name="CIB", last=139.5, change=0.95, change_pct=0.68
            ),
            TopMover(
                stock_id=2,
                symbol="ABUK",
                name="Abu Qir",
                last=91.71,
                change=-0.29,
                change_pct=-0.31,
            ),
        ]
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("top_movers")
        assert tool is not None
        result = tool.fn(market_id=1, limit=50)

        mock_client.get_top_movers.assert_called_once_with(market_id=1, limit=50)
        assert result == [
            {
                "stock_id": 1,
                "symbol": "COMI",
                "name": "CIB",
                "last": 139.5,
                "change": 0.95,
                "change_pct": 0.68,
            },
            {
                "stock_id": 2,
                "symbol": "ABUK",
                "name": "Abu Qir",
                "last": 91.71,
                "change": -0.29,
                "change_pct": -0.31,
            },
        ]

    def test_top_movers_defaults(self) -> None:
        mock_client = MagicMock()
        mock_client.get_top_movers.return_value = []
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("top_movers")
        assert tool is not None
        tool.fn()

        mock_client.get_top_movers.assert_called_once_with(market_id=1, limit=50)


class TestSellToolSettlement:
    """The settlement param (t2/t0/t1) must reach Client.sell() — it was
    previously missing from the MCP tool signature entirely, silently
    hardcoding the client's t2 default and making same-day (T0) sells
    unreachable via MCP even after the core SDK fix landed.
    """

    def setup_method(self) -> None:
        self._orig_client = mcp_server._client
        self._orig_safety = mcp_server._safety

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client
        mcp_server._safety = self._orig_safety

    def _no_cap_safety(self) -> SafetySettings:
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 0
        settings.max_daily_orders = 0
        return settings

    def test_settlement_defaults_to_t2(self) -> None:
        mock_client = MagicMock()
        mock_client.sell.return_value = Order(quantity=1, price=1.0)
        mcp_server._client = mock_client
        mcp_server._safety = self._no_cap_safety()

        sell = _sell_fn()
        sell(symbol="ABUK", qty=1, limit=1.0)

        mock_client.sell.assert_called_once_with(symbol="ABUK", qty=1, limit=1.0, settlement="t2")

    def test_settlement_t0_passed_through(self) -> None:
        mock_client = MagicMock()
        mock_client.sell.return_value = Order(quantity=1, price=1.0)
        mcp_server._client = mock_client
        mcp_server._safety = self._no_cap_safety()

        sell = _sell_fn()
        sell(symbol="ABUK", qty=1, limit=1.0, settlement="t0")

        mock_client.sell.assert_called_once_with(symbol="ABUK", qty=1, limit=1.0, settlement="t0")


class TestMarketStatusTool:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client

    def test_registered(self) -> None:
        assert mcp_server.app._tool_manager.get_tool("market_status") is not None

    def test_wraps_client_market_status(self) -> None:
        mock_client = MagicMock()
        mock_client.market_status.return_value = "open"
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("market_status")
        assert tool is not None
        result = tool.fn(market_id=1, timeout_seconds=8.0)

        mock_client.market_status.assert_called_once_with(market_id=1, timeout=8.0)
        assert result == "open"


class TestPositionsSplitTool:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client

    def test_registered(self) -> None:
        assert mcp_server.app._tool_manager.get_tool("positions_split") is not None

    def test_splits_and_serializes_stock_and_fund_positions(self) -> None:
        stock_pos = Position(quantity=10, averageCost=5.0)
        fund_pos = Position(quantity=5, averageCost=2.0)
        mock_client = MagicMock()
        mock_client.positions_split.return_value = ([stock_pos], [fund_pos])
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("positions_split")
        assert tool is not None
        result = tool.fn(market_id=1)

        mock_client.positions_split.assert_called_once_with(market_id=1)
        assert result == {
            "stock_positions": [stock_pos.model_dump()],
            "fund_positions": [fund_pos.model_dump()],
        }


class TestFundPositionsTool:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client

    def test_registered(self) -> None:
        assert mcp_server.app._tool_manager.get_tool("fund_positions") is not None

    def test_wraps_and_serializes(self) -> None:
        fp = FundPosition(fund_id=42, quantity=100, averageCost=1.0)
        mock_client = MagicMock()
        mock_client.fund_positions.return_value = [fp]
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("fund_positions")
        assert tool is not None
        result = tool.fn(market_id=1)

        mock_client.fund_positions.assert_called_once_with(market_id=1)
        assert result == [fp.model_dump()]


class TestStockClassificationTools:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client

    def test_list_by_class_registered_and_wraps(self) -> None:
        stock = StockInfo(stockId=1, symbol="SUCE", security_class_name="OTC")
        mock_client = MagicMock()
        mock_client.list_by_class.return_value = [stock]
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("list_by_class")
        assert tool is not None
        result = tool.fn(class_names=["OTC"])

        mock_client.list_by_class.assert_called_once_with("OTC")
        assert result == [stock.model_dump()]

    def test_list_same_day_eligible_registered_and_wraps(self) -> None:
        stock = StockInfo(stockId=2, symbol="ABUK", is_same_day_eligible=True)
        mock_client = MagicMock()
        mock_client.list_same_day_eligible.return_value = [stock]
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("list_same_day_eligible")
        assert tool is not None
        result = tool.fn()

        mock_client.list_same_day_eligible.assert_called_once_with()
        assert result == [stock.model_dump()]

    def test_list_otc_registered_and_wraps(self) -> None:
        stock = StockInfo(stockId=3, symbol="SUCE", security_class_name="OTC")
        mock_client = MagicMock()
        mock_client.list_otc.return_value = [stock]
        mcp_server._client = mock_client

        tool = mcp_server.app._tool_manager.get_tool("list_otc")
        assert tool is not None
        result = tool.fn()

        mock_client.list_otc.assert_called_once_with()
        assert result == [stock.model_dump()]


class TestFundOrderTools:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client
        self._orig_safety = mcp_server._safety

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client
        mcp_server._safety = self._orig_safety

    def test_buy_fund_registered_and_wraps(self) -> None:
        mock_client = MagicMock()
        mock_client.buy_fund.return_value = Order(fund_id=7, quantity=1, price=1.0)
        mcp_server._client = mock_client
        mcp_server._safety = _no_cap_safety()

        buy_fund = _buy_fund_fn()
        result = buy_fund(fund_id=7, qty=1, price=1.0)

        mock_client.buy_fund.assert_called_once_with(fund_id=7, qty=1, price=1.0, is_ipo_fund=False)
        assert result["fund_id"] == 7

    def test_buy_fund_rejects_order_exceeding_safety_cap(self) -> None:
        mock_client = MagicMock()
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 100  # tiny cap
        settings.max_daily_orders = 0
        mcp_server._safety = settings

        buy_fund = _buy_fund_fn()
        with pytest.raises(ValueError, match="safety cap"):
            buy_fund(fund_id=7, qty=1000, price=100.0)  # 100,000 EGP > 100

        mock_client.buy_fund.assert_not_called()

    def test_sell_fund_registered_and_wraps(self) -> None:
        mock_client = MagicMock()
        mock_client.sell_fund.return_value = Order(fund_id=7, quantity=1, price=1.0)
        mcp_server._client = mock_client
        mcp_server._safety = _no_cap_safety()

        sell_fund = _sell_fund_fn()
        result = sell_fund(fund_id=7, qty=1, price=1.0)

        mock_client.sell_fund.assert_called_once_with(fund_id=7, qty=1, price=1.0)
        assert result["fund_id"] == 7

    def test_cancel_fund_order_registered_and_wraps(self) -> None:
        mock_client = MagicMock()
        mock_client.cancel_fund_order.return_value = True
        mcp_server._client = mock_client

        cancel_fund_order = _cancel_fund_order_fn()
        result = cancel_fund_order(order_id=123)

        mock_client.cancel_fund_order.assert_called_once_with(123)
        assert result == {"success": True, "order_id": 123}


class TestAmendOrderSafetyCheck:
    def setup_method(self) -> None:
        self._orig_client = mcp_server._client
        self._orig_safety = mcp_server._safety

    def teardown_method(self) -> None:
        mcp_server._client = self._orig_client
        mcp_server._safety = self._orig_safety

    def test_rejects_amendment_exceeding_cap(self) -> None:
        mock_client = MagicMock()
        mock_client.get_order.return_value = Order(quantity=10, price=5.0)
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 100  # tiny cap
        mcp_server._safety = settings

        amend_order = _amend_order_fn()
        with pytest.raises(ValueError, match="safety cap"):
            amend_order(order_id=1, qty=1000, price=100.0)  # 100,000 EGP > 100

        mock_client.amend_order.assert_not_called()

    def test_allows_amendment_within_cap(self) -> None:
        mock_client = MagicMock()
        mock_client.get_order.return_value = Order(quantity=10, price=5.0)
        mock_client.amend_order.return_value = True
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 100_000
        mcp_server._safety = settings

        amend_order = _amend_order_fn()
        result = amend_order(order_id=1, qty=100, price=50.0)  # 5,000 EGP < 100,000

        assert result == {"success": True, "order_id": 1}
        mock_client.amend_order.assert_called_once_with(1, qty=100, price=50.0)

    def test_partial_qty_only_amendment_uses_current_price_for_check(self) -> None:
        # price omitted -> effective price must come from the CURRENT order
        # (50.0), not be skipped just because price=None.
        mock_client = MagicMock()
        mock_client.get_order.return_value = Order(quantity=10, price=50.0)
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 1_000  # tiny cap
        mcp_server._safety = settings

        amend_order = _amend_order_fn()
        with pytest.raises(ValueError, match="safety cap"):
            amend_order(order_id=1, qty=1000)  # 1000 * current price 50.0 = 50,000 > 1,000

        mock_client.amend_order.assert_not_called()

    def test_partial_price_only_amendment_uses_current_qty_for_check(self) -> None:
        # qty omitted -> effective qty must come from the CURRENT order
        # (2000), not be skipped just because qty=None.
        mock_client = MagicMock()
        mock_client.get_order.return_value = Order(quantity=2000, price=1.0)
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 1_000  # tiny cap
        mcp_server._safety = settings

        amend_order = _amend_order_fn()
        with pytest.raises(ValueError, match="safety cap"):
            amend_order(order_id=1, price=50.0)  # current qty 2000 * 50.0 = 100,000 > 1,000

        mock_client.amend_order.assert_not_called()

    def test_disabled_cap_allows_any_amendment(self) -> None:
        mock_client = MagicMock()
        mock_client.get_order.return_value = Order(quantity=10, price=5.0)
        mock_client.amend_order.return_value = True
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 0  # disabled
        mcp_server._safety = settings

        amend_order = _amend_order_fn()
        result = amend_order(order_id=1, qty=1_000_000, price=10_000.0)

        assert result == {"success": True, "order_id": 1}

    def test_missing_qty_and_price_rejected_before_touching_client(self) -> None:
        mock_client = MagicMock()
        mcp_server._client = mock_client
        settings = SafetySettings.__new__(SafetySettings)
        settings.max_order_value_egp = 100_000
        mcp_server._safety = settings

        amend_order = _amend_order_fn()
        result = amend_order(order_id=1)

        assert result == {
            "success": False,
            "error": "At least one of qty or price must be provided.",
        }
        mock_client.get_order.assert_not_called()
        mock_client.amend_order.assert_not_called()
