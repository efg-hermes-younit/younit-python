"""Unit tests for the streaming module.

All Lightstreamer interactions are mocked with a FakeLightstreamerClient and
FakeLSSubscription so no real network connection is required.

Test areas:
- StreamingClient connection management (connect, disconnect, is_connected)
- Token injection and update
- subscribe_quote / subscribe_index / subscribe_market / subscribe_trades / subscribe_orders
- subscribe_raw
- unsubscribe
- Callback invocation with correct parsed model types
- Error callbacks on subscription errors
- ConnectionFailed on timeout
- SubscriptionFailed propagation
- parsers module field lists (sanity check)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from younit import config
from younit.config import Settings
from younit.exceptions import ConnectionFailed, StreamingError, SubscriptionFailed
from younit.models.streaming import (
    IndexUpdate,
    MarketUpdate,
    OrderUpdate,
    Subscription,
    SymbolUpdate,
    TradeUpdate,
    _bool,
    _float,
    _int,
)
from younit.streaming.client import (
    StreamingClient,
    _SubscriptionListener,
)
from younit.streaming.parsers import (
    INDEX_FIELDS,
    MARKET_FIELDS,
    ORDER_FIELDS,
    SYMBOL_FIELDS,
    TRADE_FIELDS,
)

# ---------------------------------------------------------------------------
# Helpers — minimal fake Lightstreamer objects
# ---------------------------------------------------------------------------


class FakeLSSubscription:
    """Minimal stand-in for lightstreamer.client.Subscription."""

    def __init__(self, mode: str, items: list[str], fields: list[str]) -> None:
        self.mode = mode
        self.items = items
        self.fields = fields
        self._data_adapter: str | None = None
        self._snapshot: str | None = None
        self._listeners: list[Any] = []

    def setDataAdapter(self, adapter: str) -> None:  # noqa: N802
        self._data_adapter = adapter

    def setRequestedSnapshot(self, snapshot: str) -> None:  # noqa: N802
        self._snapshot = snapshot

    def addListener(self, listener: Any) -> None:  # noqa: N802
        self._listeners.append(listener)


class FakeLSClient:
    """Minimal stand-in for lightstreamer.client.LightstreamerClient."""

    def __init__(self, url: str, adapter: str) -> None:
        self.url = url
        self.adapter = adapter
        self._listeners: list[Any] = []
        self._subscriptions: list[Any] = []
        self.connectionDetails = MagicMock()

    def addListener(self, listener: Any) -> None:  # noqa: N802
        self._listeners.append(listener)

    def connect(self) -> None:
        # Immediately signal connected to all listeners
        for listener in self._listeners:
            listener.onStatusChange("CONNECTED:WS-STREAMING")

    def subscribe(self, sub: Any) -> None:
        self._subscriptions.append(sub)

    def unsubscribe(self, sub: Any) -> None:
        self._subscriptions = [s for s in self._subscriptions if s is not sub]

    def disconnect(self) -> None:
        for listener in self._listeners:
            listener.onStatusChange("DISCONNECTED")


def _fake_ls_module(fake_client_cls=FakeLSClient, fake_sub_cls=FakeLSSubscription):
    """Return a mock lightstreamer.client module."""
    mod = MagicMock()
    mod.LightstreamerClient = fake_client_cls
    mod.Subscription = fake_sub_cls
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings(
        trading_id="trading-123",
        api_key="test-key",
        streaming_adapter="PROXY_MarketBeat",
        simulation=True,
    )


@pytest.fixture
def token_getter():
    return MagicMock(return_value="fake-token")


@pytest.fixture
def symbol_resolver():
    return MagicMock(side_effect=lambda sym: 9999 if sym.upper() == "COMI" else 1111)


@pytest.fixture
def streaming_client(settings, token_getter, symbol_resolver) -> StreamingClient:
    return StreamingClient(
        settings=settings,
        token_getter=token_getter,
        symbol_resolver=symbol_resolver,
    )


# ---------------------------------------------------------------------------
# Tests — connection management
# ---------------------------------------------------------------------------


class TestConnection:
    def test_not_connected_initially(self, streaming_client):
        assert streaming_client.is_connected() is False

    def test_connect_sets_connected(self, streaming_client):
        with patch("younit.streaming.client.importlib", create=True):
            with patch.dict(
                "sys.modules",
                {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
            ):
                streaming_client.connect()
        assert streaming_client.is_connected() is True

    def test_connect_idempotent(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
            streaming_client.connect()  # second call should be no-op
        assert streaming_client.is_connected() is True

    def test_login_uses_trading_id_and_token(self, streaming_client, settings, token_getter):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
        details = streaming_client._ls_client.connectionDetails
        details.setUser.assert_called_once_with(settings.trading_id)
        details.setPassword.assert_called_once_with(token_getter.return_value)

    def test_disconnect_resets_state(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
            streaming_client.disconnect()
        assert streaming_client.is_connected() is False

    def test_disconnect_when_not_connected_is_safe(self, streaming_client):
        streaming_client.disconnect()  # should not raise

    def test_missing_library_raises_streaming_error(self, streaming_client):
        with patch.dict("sys.modules", {"lightstreamer": None, "lightstreamer.client": None}):
            with pytest.raises(StreamingError, match="lightstreamer-client-lib"):
                streaming_client.connect()

    def test_connect_timeout_raises_connection_failed(
        self, settings, token_getter, symbol_resolver
    ):
        """If the LS client never reports CONNECTED the timeout should fire."""

        class SlowLSClient(FakeLSClient):
            def connect(self) -> None:
                pass  # Never calls onStatusChange("CONNECTED")

        sc = StreamingClient(
            settings=settings,
            token_getter=token_getter,
            symbol_resolver=symbol_resolver,
        )
        # Patch timeout down to 0.1s for speed
        with patch("younit.streaming.client._CONNECT_TIMEOUT", 0.1):
            with patch.dict(
                "sys.modules",
                {
                    "lightstreamer": MagicMock(),
                    "lightstreamer.client": _fake_ls_module(fake_client_cls=SlowLSClient),
                },
            ):
                with pytest.raises(ConnectionFailed, match="timed out"):
                    sc.connect()

    def test_connect_uses_streaming_url_constant(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
        assert streaming_client._ls_client.url == config._STREAMING_URL

    def test_connect_uses_streaming_url_regardless_of_simulation(
        self, token_getter, symbol_resolver
    ):
        """Sim streaming is discontinued — simulation must not change the streaming host."""
        real_settings = Settings(trading_id="trading-123", api_key="test-key", simulation=False)
        sc = StreamingClient(
            settings=real_settings, token_getter=token_getter, symbol_resolver=symbol_resolver
        )
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sc.connect()
        assert sc._ls_client.url == config._STREAMING_URL


# ---------------------------------------------------------------------------
# Tests — token update
# ---------------------------------------------------------------------------


class TestTokenUpdate:
    def test_update_token_when_connected(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
            streaming_client.update_token("new-token")
            streaming_client._ls_client.connectionDetails.setPassword.assert_called_with(
                "new-token"
            )

    def test_update_token_when_not_connected_is_safe(self, streaming_client):
        streaming_client.update_token("new-token")  # should not raise


# ---------------------------------------------------------------------------
# Tests — subscribe methods
# ---------------------------------------------------------------------------


class TestSubscribeMethods:
    def _connect(self, sc: StreamingClient) -> None:
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sc.connect()

    def test_subscribe_quote_returns_subscription(self, streaming_client, symbol_resolver):
        self._connect(streaming_client)
        called: list[SymbolUpdate] = []
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_quote("COMI", on_update=called.append)

        assert isinstance(sub, Subscription)
        assert sub.stream_type == "SymbolStatistics"
        assert sub.item == "sy9999"
        symbol_resolver.assert_called_with("COMI")

    def test_subscribe_index_returns_subscription(self, streaming_client):
        self._connect(streaming_client)
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_index(1, on_update=lambda _: None)

        assert isinstance(sub, Subscription)
        assert sub.stream_type == "IndexStatistics"
        assert sub.item == "ix1"

    def test_subscribe_market_returns_subscription(self, streaming_client):
        self._connect(streaming_client)
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_market(1, on_update=lambda _: None)

        assert sub.stream_type == "MarketStatistics"
        assert sub.item == "mk1"

    def test_subscribe_trades_returns_subscription(self, streaming_client):
        self._connect(streaming_client)
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_trades("COMI", on_update=lambda _: None)

        assert sub.stream_type == "SecurityTrades"
        assert sub.item == "ts9999"

    def test_subscribe_orders_uses_trading_id(self, streaming_client, settings):
        self._connect(streaming_client)
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_orders(on_update=lambda _: None)

        assert sub.stream_type == "ActiveOrders"
        assert sub.item == f"po{settings.trading_id}"

    def test_subscribe_orders_custom_account_id(self, streaming_client):
        self._connect(streaming_client)
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_orders(
                on_update=lambda _: None,
                client_account_id="custom-id-99",
            )
        assert sub.item == "pocustom-id-99"

    def test_subscribe_connects_automatically(self, streaming_client):
        assert not streaming_client.is_connected()
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.subscribe_index(1, on_update=lambda _: None)
        assert streaming_client.is_connected()


# ---------------------------------------------------------------------------
# Tests — unsubscribe
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    def test_unsubscribe_removes_from_active_list(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_index(1, on_update=lambda _: None)
            assert sub in streaming_client._active_subs
            streaming_client.unsubscribe(sub)
        assert sub not in streaming_client._active_subs

    def test_unsubscribe_when_not_connected_is_safe(self, streaming_client):
        fake_sub = Subscription(
            stream_type="SymbolStatistics",
            item="sy999",
            on_update=lambda _: None,
        )
        streaming_client.unsubscribe(fake_sub)  # should not raise

    def test_unsubscribe_composite_handle_tears_down_all_children(self, streaming_client):
        """A composite Subscription (e.g. from Client.stream_top_movers) whose
        _ls_subscription is a list of child Subscriptions unsubscribes every
        child, not just the composite handle itself."""
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            child_a = streaming_client.subscribe_index(1, on_update=lambda _: None)
            child_b = streaming_client.subscribe_index(2, on_update=lambda _: None)
            assert child_a in streaming_client._active_subs
            assert child_b in streaming_client._active_subs

            composite = Subscription(
                stream_type="TopMovers",
                item="top_movers[2]",
                on_update=lambda _: None,
                _ls_subscription=[child_a, child_b],
            )
            streaming_client.unsubscribe(composite)

        assert child_a not in streaming_client._active_subs
        assert child_b not in streaming_client._active_subs


# ---------------------------------------------------------------------------
# Tests — callback invocation with correct parsed model types
# ---------------------------------------------------------------------------


class TestCallbacks:
    def _make_fake_item_update(self, fields: dict[str, str | None]) -> Any:
        """Fake ItemUpdate object with getValue() and a .fields attribute."""
        update = MagicMock()
        update.fields = list(fields.keys())
        update.getValue = MagicMock(side_effect=lambda f: fields.get(f))
        return update

    def test_symbol_update_callback_receives_symbol_update(self, streaming_client):
        received: list[SymbolUpdate] = []
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_quote("COMI", on_update=received.append)

        # Simulate an item update from Lightstreamer
        raw = {
            "m_SymbolID": "9999",
            "m_ShortName": "COMI",
            "m_LastTradePrice": "45.50",
            "m_Change": "1.20",
            "m_PercentChange": "2.71",
            "m_BidPrice": "45.40",
            "m_AskPrice": "45.60",
            "m_TradedVolume": "1500000",
        }
        ls_sub = sub._ls_subscription
        listener = ls_sub._listeners[0]
        listener.onItemUpdate(self._make_fake_item_update(raw))

        assert len(received) == 1
        update = received[0]
        assert isinstance(update, SymbolUpdate)
        assert update.symbol == "COMI"
        assert update.last == 45.50
        assert update.change == 1.20
        assert update.change_pct == 2.71
        assert update.bid == 45.40
        assert update.volume == 1_500_000

    def test_order_update_callback_receives_order_update(self, streaming_client):
        received: list[OrderUpdate] = []
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_orders(on_update=received.append)

        raw = {
            "key": "abc123",
            "command": "ADD",
            "m_OrderNumber": "ORD-001",
            "m_OrderStatus": "1",
            "m_OrderStatusUI": "Submitted",
            "m_OrderQuantity": "100",
            "m_OrderExecQuantity": "0",
            "m_OrderPrice": "45.50",
            "m_SymbolID": "9999",
            "m_IsOrderLocked": "false",
        }
        ls_sub = sub._ls_subscription
        listener = ls_sub._listeners[0]
        listener.onItemUpdate(self._make_fake_item_update(raw))

        assert len(received) == 1
        update = received[0]
        assert isinstance(update, OrderUpdate)
        assert update.command == "ADD"
        assert update.order_number == "ORD-001"
        assert update.status_ui == "Submitted"
        assert update.quantity == 100
        assert update.executed_quantity == 0
        assert update.is_locked is False

    def test_trade_update_callback_receives_trade_update(self, streaming_client):
        received: list[TradeUpdate] = []
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_trades("COMI", on_update=received.append)

        raw = {
            "key": "t1",
            "command": "ADD",
            "m_SymbolID": "9999",
            "m_TradePrice": "45.30",
            "m_TradeVolume": "500",
            "m_TicketNumber": "TKT-999",
        }
        ls_sub = sub._ls_subscription
        listener = ls_sub._listeners[0]
        listener.onItemUpdate(self._make_fake_item_update(raw))

        assert len(received) == 1
        update = received[0]
        assert isinstance(update, TradeUpdate)
        assert update.command == "ADD"
        assert update.price == 45.30
        assert update.volume == 500

    def test_callback_exception_calls_on_error(self, streaming_client):
        """If the on_update callback raises, on_error should be called."""
        errors: list[Exception] = []

        def bad_callback(update: SymbolUpdate) -> None:
            raise ValueError("callback error")

        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_quote(
                "COMI",
                on_update=bad_callback,
                on_error=errors.append,
            )

        raw = {"m_ShortName": "COMI", "m_LastTradePrice": "45.00"}
        ls_sub = sub._ls_subscription
        listener = ls_sub._listeners[0]
        listener.onItemUpdate(self._make_fake_item_update(raw))

        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)


# ---------------------------------------------------------------------------
# Tests — SubscriptionListener error handling
# ---------------------------------------------------------------------------


class TestSubscriptionListener:
    def test_on_subscription_error_raises_and_calls_error_cb(self):
        errors: list[Exception] = []
        listener = _SubscriptionListener(
            on_update=lambda _: None,
            on_error=errors.append,
            item="sy999",
            fields=["m_LastPrice"],
            stream_type="SymbolStatistics",
        )
        with pytest.raises(SubscriptionFailed, match="Subscription error"):
            listener.onSubscriptionError(42, "No such item")

        assert len(errors) == 1
        assert isinstance(errors[0], SubscriptionFailed)
        assert errors[0].code == 42


# ---------------------------------------------------------------------------
# Tests — parsed model type helpers
# ---------------------------------------------------------------------------


class TestTypeHelpers:
    def test_float_coercion(self):
        assert _float("45.50") == 45.50
        assert _float(None) is None
        assert _float("n/a") is None
        assert _float("") is None

    def test_int_coercion(self):
        assert _int("100") == 100
        assert _int("100.0") == 100
        assert _int(None) is None
        assert _int("abc") is None

    def test_bool_coercion(self):
        assert _bool("true") is True
        assert _bool("True") is True
        assert _bool("1") is True
        assert _bool("false") is False
        assert _bool("0") is False
        assert _bool(None) is None


# ---------------------------------------------------------------------------
# Tests — SymbolUpdate / IndexUpdate / MarketUpdate model construction
# ---------------------------------------------------------------------------


class TestUpdateModels:
    def test_symbol_update_all_none_on_empty_raw(self):
        u = SymbolUpdate({})
        assert u.stock_id is None
        assert u.last is None
        assert u.volume is None

    def test_index_update_parses_typo_field(self):
        """The API has a typo: m_PrecentChange (not m_PercentChange)."""
        u = IndexUpdate({"m_PrecentChange": "1.23"})
        assert u.change_pct == 1.23

    def test_market_update_status(self):
        u = MarketUpdate({"m_MarketStatus": "Open", "m_MarketID": "1"})
        assert u.status == "Open"
        assert u.market_id == 1

    def test_order_update_delete_command(self):
        u = OrderUpdate({"command": "DELETE", "key": "k1", "m_OrderNumber": "ORD-1"})
        assert u.command == "DELETE"
        assert u.order_number == "ORD-1"

    def test_order_update_profile_id_coerced_to_int(self):
        """m_ClientAccProfileID arrives as a raw string from Lightstreamer."""
        u = OrderUpdate({"m_ClientAccProfileID": "10413324"})
        assert u.profile_id == 10413324
        assert isinstance(u.profile_id, int)

    def test_order_update_status_coerced_to_int(self):
        """m_OrderStatus arrives as a raw string from Lightstreamer."""
        u = OrderUpdate({"m_OrderStatus": "7"})
        assert u.status == 7
        assert isinstance(u.status, int)

    def test_order_update_profile_id_and_status_none_on_missing(self):
        u = OrderUpdate({})
        assert u.profile_id is None
        assert u.status is None


# ---------------------------------------------------------------------------
# Tests — parsers module field lists sanity
# ---------------------------------------------------------------------------


class TestParsers:
    def test_symbol_fields_contains_required(self):
        assert "m_LastTradePrice" in SYMBOL_FIELDS
        assert "m_BidPrice" in SYMBOL_FIELDS
        assert "m_AskPrice" in SYMBOL_FIELDS
        assert "m_TradedVolume" in SYMBOL_FIELDS
        assert "m_PercentChange" in SYMBOL_FIELDS

    def test_order_fields_contains_required(self):
        assert "key" in ORDER_FIELDS
        assert "command" in ORDER_FIELDS
        assert "m_OrderNumber" in ORDER_FIELDS
        assert "m_OrderStatus" in ORDER_FIELDS
        assert "m_OrderQuantity" in ORDER_FIELDS
        assert "m_OrderExecQuantity" in ORDER_FIELDS

    def test_trade_fields_contains_required(self):
        assert "key" in TRADE_FIELDS
        assert "command" in TRADE_FIELDS
        assert "m_TradePrice" in TRADE_FIELDS
        assert "m_TradeVolume" in TRADE_FIELDS

    def test_index_fields_contains_required(self):
        assert "m_IndexValue" in INDEX_FIELDS
        assert "m_PrecentChange" in INDEX_FIELDS  # intentional typo from API

    def test_market_fields_contains_required(self):
        assert "m_MarketStatus" in MARKET_FIELDS
        assert "m_TradedValue" in MARKET_FIELDS
        assert "m_TradesCount" in MARKET_FIELDS

    def test_no_duplicate_fields(self):
        for name, fields in [
            ("SYMBOL_FIELDS", SYMBOL_FIELDS),
            ("INDEX_FIELDS", INDEX_FIELDS),
            ("MARKET_FIELDS", MARKET_FIELDS),
            ("TRADE_FIELDS", TRADE_FIELDS),
            ("ORDER_FIELDS", ORDER_FIELDS),
        ]:
            assert len(fields) == len(set(fields)), f"Duplicate in {name}"


# ---------------------------------------------------------------------------
# Tests — error-handling branches not exercised by the happy-path suite above
# ---------------------------------------------------------------------------


class TestConnectionErrorBranches:
    def test_disconnect_swallows_underlying_exception(self, streaming_client):
        class BrokenDisconnectClient(FakeLSClient):
            def disconnect(self) -> None:
                raise RuntimeError("disconnect boom")

        with patch.dict(
            "sys.modules",
            {
                "lightstreamer": MagicMock(),
                "lightstreamer.client": _fake_ls_module(fake_client_cls=BrokenDisconnectClient),
            },
        ):
            streaming_client.connect()
            streaming_client.disconnect()  # should not raise
        assert streaming_client.is_connected() is False

    def test_update_token_swallows_underlying_exception(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
            streaming_client._ls_client.connectionDetails.setPassword.side_effect = RuntimeError(
                "boom"
            )
            streaming_client.update_token("new-token")  # should not raise

    def test_on_server_error_unblocks_connect_waiter(self, streaming_client):
        class ErroringLSClient(FakeLSClient):
            def connect(self) -> None:
                for listener in self._listeners:
                    listener.onServerError(17, "bad credentials")

        with patch.dict(
            "sys.modules",
            {
                "lightstreamer": MagicMock(),
                "lightstreamer.client": _fake_ls_module(fake_client_cls=ErroringLSClient),
            },
        ):
            streaming_client.connect()
        assert streaming_client.is_connected() is False


class TestSubscribeOrdersProfileIdGetter:
    def test_uses_profile_id_getter_when_available(self, settings, token_getter, symbol_resolver):
        sc = StreamingClient(
            settings=settings,
            token_getter=token_getter,
            symbol_resolver=symbol_resolver,
            profile_id_getter=MagicMock(return_value=55555),
        )
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = sc.subscribe_orders(on_update=lambda _: None)
        assert sub.item == "po55555"

    def test_falls_back_to_trading_id_when_getter_returns_none(
        self, settings, token_getter, symbol_resolver
    ):
        sc = StreamingClient(
            settings=settings,
            token_getter=token_getter,
            symbol_resolver=symbol_resolver,
            profile_id_getter=MagicMock(return_value=None),
        )
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = sc.subscribe_orders(on_update=lambda _: None)
        assert sub.item == f"po{settings.trading_id}"


class TestUnsubscribeErrorBranch:
    def test_unsubscribe_wraps_exception_in_streaming_error(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            sub = streaming_client.subscribe_index(1, on_update=lambda _: None)
            streaming_client._ls_client.unsubscribe = MagicMock(
                side_effect=RuntimeError("unsub boom")
            )
            with pytest.raises(StreamingError, match="Failed to unsubscribe"):
                streaming_client.unsubscribe(sub)


class TestSubscribeRawErrorBranches:
    def test_subscription_failed_from_make_ls_subscription_is_not_rewrapped(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
            streaming_client._make_ls_subscription = MagicMock(
                side_effect=SubscriptionFailed("nope", code=1, error_message="nope")
            )
            with pytest.raises(SubscriptionFailed, match="nope"):
                streaming_client.subscribe_index(1, on_update=lambda _: None)

    def test_generic_exception_is_wrapped_in_subscription_failed(self, streaming_client):
        with patch.dict(
            "sys.modules",
            {"lightstreamer": MagicMock(), "lightstreamer.client": _fake_ls_module()},
        ):
            streaming_client.connect()
            streaming_client._make_ls_subscription = MagicMock(
                side_effect=RuntimeError("weird failure")
            )
            with pytest.raises(SubscriptionFailed, match="Failed to subscribe"):
                streaming_client.subscribe_index(1, on_update=lambda _: None)


class TestSubscriptionListenerMisc:
    def test_on_error_callback_failure_is_swallowed(self):
        """If the user's on_error callback itself raises, it must not propagate."""
        listener = _SubscriptionListener(
            on_update=lambda _: None,
            on_error=MagicMock(side_effect=RuntimeError("on_error boom")),
            item="sy999",
            fields=["m_LastPrice"],
            stream_type="SymbolStatistics",
        )
        with pytest.raises(SubscriptionFailed):
            listener.onSubscriptionError(1, "boom")

    def test_on_update_error_with_no_error_callback_does_not_raise(self):
        listener = _SubscriptionListener(
            on_update=MagicMock(side_effect=ValueError("bad update")),
            on_error=None,
            item="sy999",
            fields=["m_LastPrice"],
            stream_type="SymbolStatistics",
        )
        update = MagicMock()
        update.getValue = MagicMock(return_value="1.0")
        listener.onItemUpdate(update)  # should not raise

    def test_on_lost_updates_logs_without_raising(self):
        listener = _SubscriptionListener(
            on_update=lambda _: None,
            on_error=None,
            item="sy999",
            fields=["m_LastPrice"],
            stream_type="SymbolStatistics",
        )
        listener.onLostUpdates("sy999", 1, 5)  # should not raise
