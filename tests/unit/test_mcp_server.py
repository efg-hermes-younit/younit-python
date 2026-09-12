"""Unit tests for MCP server tool handlers (src/younit/mcp_server/server.py).

Only ``amend_order`` is covered here — ``amend_fund_order`` has no MCP tool
handler at all (no ``buy_fund``/``sell_fund``/``cancel_fund_order``/
``amend_fund_order`` tools are registered anywhere in server.py; fund orders
are only reachable via the SDK's ``Client``, never via the MCP server), so
there is nothing to test for it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from younit.mcp_server import server as mcp_server
from younit.mcp_server.safety import SafetySettings
from younit.models.orders import Order


def _amend_order_fn():
    mcp_server._register_write_tools()
    tool = mcp_server.app._tool_manager.get_tool("amend_order")
    assert tool is not None
    return tool.fn


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
