"""StreamingClient — wraps the Lightstreamer Python client library.

This module connects to the real-time data feed via Lightstreamer
and exposes subscribe_* methods for each of the five available stream types:

- ``subscribe_quote``   — SymbolStatistics per stock
- ``subscribe_index``   — IndexStatistics per index
- ``subscribe_market``  — MarketStatistics per market
- ``subscribe_trades``  — SecurityTrades (trade tape) per stock
- ``subscribe_orders``  — ActiveOrders (live order book) per client account

Usage::

    # Connect is called automatically on first subscribe, or explicitly:
    client.streaming.connect()

    sub = client.streaming.subscribe_quote(
        "COMI",
        on_update=lambda update: print(f"{update.symbol}: {update.last} EGP"),
    )

    # Later:
    client.streaming.unsubscribe(sub)
    client.streaming.disconnect()
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from younit.config import _STREAMING_URL
from younit.exceptions import ConnectionFailed, StreamingError, SubscriptionFailed
from younit.logging import get_logger
from younit.models.streaming import (
    IndexUpdate,
    MarketUpdate,
    OrderUpdate,
    Subscription,
    SymbolUpdate,
    TradeUpdate,
)
from younit.streaming.parsers import (
    INDEX_FIELDS,
    MARKET_FIELDS,
    ORDER_FIELDS,
    SYMBOL_FIELDS,
    TRADE_FIELDS,
)

if TYPE_CHECKING:
    from younit.config import Settings

_log = get_logger(__name__)

# Lightstreamer subscription modes
_MODE_MERGE = "MERGE"
_MODE_COMMAND = "COMMAND"

# How long (seconds) to wait for the Lightstreamer connection to be
# established before raising ConnectionFailed.
_CONNECT_TIMEOUT = 30.0


class StreamingClient:
    """Real-time streaming client for the trading platform.

    Wraps the Lightstreamer Python client library.  Subscriptions run on
    Lightstreamer's background thread.  User callbacks are invoked on that
    thread — keep them fast and non-blocking.

    Token refresh: when the SDK refreshes the client token, call
    :meth:`update_token` to push the new token to Lightstreamer without
    disconnecting.

    Args:
        settings: The SDK :class:`~younit.config.Settings` instance.
        token_getter: Callable that returns the current valid client token.
        symbol_resolver: Callable that maps a ticker string to a stock ID.

    Example::

        sub = client.streaming.subscribe_quote(
            "HRHO",
            on_update=lambda u: print(f"{u.symbol}: {u.last}"),
        )
        # ...
        client.streaming.unsubscribe(sub)
    """

    def __init__(
        self,
        settings: Settings,
        token_getter: Callable[[], str],
        symbol_resolver: Callable[[str], int],
        profile_id_getter: Callable[[], int | None] | None = None,
    ) -> None:
        self._settings = settings
        self._token_getter = token_getter
        self._symbol_resolver = symbol_resolver
        self._profile_id_getter = profile_id_getter

        self._ls_client: Any = None  # LightstreamerClient, imported lazily
        self._lock = threading.RLock()  # RLock: token_getter re-enters during _do_connect
        self._connected = False
        self._connect_event = threading.Event()
        self._active_subs: list[Subscription] = []

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the Lightstreamer server.

        Blocks until the connection is established or raises
        :class:`~younit.exceptions.ConnectionFailed` on timeout.

        This is called automatically on the first ``subscribe_*`` call.
        You only need to call it explicitly if you want to pre-warm the
        connection before subscribing.

        Raises:
            ConnectionFailed: If the connection cannot be established within
                ``_CONNECT_TIMEOUT`` seconds.
        """
        with self._lock:
            if self._connected:
                return
            self._connect_event.clear()
            self._do_connect()

        if not self._connect_event.wait(timeout=_CONNECT_TIMEOUT):
            raise ConnectionFailed(
                f"Lightstreamer connection timed out after {_CONNECT_TIMEOUT}s. "
                f"Check network connectivity to {_STREAMING_URL}.",
                status="TIMEOUT",
            )

    def disconnect(self) -> None:
        """Disconnect from Lightstreamer.

        Implicitly unsubscribes all active subscriptions.
        Safe to call even if not connected.
        """
        with self._lock:
            if self._ls_client is not None:
                _log.info("streaming_disconnect")
                try:
                    self._ls_client.disconnect()
                except Exception as exc:
                    _log.warning("streaming_disconnect_error", error=str(exc))
                self._connected = False
                self._active_subs.clear()

    def is_connected(self) -> bool:
        """Return True if currently connected to Lightstreamer."""
        return self._connected

    def update_token(self, new_token: str) -> None:
        """Push a refreshed bearer token to the Lightstreamer connection.

        Called automatically by the :class:`~younit.client.Client` when
        the client token is refreshed.  Updates the connection password
        without disconnecting.

        Args:
            new_token: The new bearer token string.
        """
        with self._lock:
            if self._ls_client is not None and self._connected:
                try:
                    self._ls_client.connectionDetails.setPassword(new_token)
                    _log.debug("streaming_token_updated")
                except Exception as exc:
                    _log.warning("streaming_token_update_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Named subscribe methods
    # ------------------------------------------------------------------

    def subscribe_quote(
        self,
        symbol: str,
        on_update: Callable[[SymbolUpdate], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> Subscription:
        """Subscribe to live price updates for a stock (SymbolStatistics stream).

        Delivers real-time bid/ask, last price, volume, and change data.
        Callbacks fire on Lightstreamer's background thread — keep them fast.

        Args:
            symbol: EGX ticker (e.g. ``"COMI"``).
            on_update: Called with a :class:`~younit.models.streaming.SymbolUpdate`
                on every price update.
            on_error: Optional error callback for subscription-level errors.

        Returns:
            :class:`~younit.models.streaming.Subscription` handle.

        Raises:
            InvalidSymbol: If the ticker is not in the symbol cache.
            ConnectionFailed: If the Lightstreamer connection fails.

        Example::

            sub = client.streaming.subscribe_quote(
                "COMI",
                on_update=lambda u: print(f"{u.symbol}: {u.last:.2f} EGP"),
            )
        """
        stock_id = self._symbol_resolver(symbol)
        item = f"sy{stock_id}"

        def _callback(raw: dict[str, str | None]) -> None:
            on_update(SymbolUpdate(raw))

        return self.subscribe_raw(
            mode=_MODE_MERGE,
            item=item,
            fields=SYMBOL_FIELDS,
            on_update=_callback,
            on_error=on_error,
            stream_type="SymbolStatistics",
        )

    def subscribe_index(
        self,
        index_id: int,
        on_update: Callable[[IndexUpdate], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> Subscription:
        """Subscribe to live value updates for a market index (IndexStatistics stream).

        Args:
            index_id: Internal index identifier (e.g. ``1`` for the EGX30 index).
            on_update: Called with a :class:`~younit.models.streaming.IndexUpdate`.
            on_error: Optional error callback.

        Returns:
            :class:`~younit.models.streaming.Subscription` handle.

        Raises:
            ConnectionFailed: If the Lightstreamer connection fails.
        """
        item = f"ix{index_id}"

        def _callback(raw: dict[str, str | None]) -> None:
            on_update(IndexUpdate(raw))

        return self.subscribe_raw(
            mode=_MODE_MERGE,
            item=item,
            fields=INDEX_FIELDS,
            on_update=_callback,
            on_error=on_error,
            stream_type="IndexStatistics",
        )

    def subscribe_market(
        self,
        market_id: int = 1,
        on_update: Callable[[MarketUpdate], None] = lambda _: None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> Subscription:
        """Subscribe to aggregated market statistics (MarketStatistics stream).

        Args:
            market_id: Market identifier (``1`` = EGX, default).
            on_update: Called with a :class:`~younit.models.streaming.MarketUpdate`.
            on_error: Optional error callback.

        Returns:
            :class:`~younit.models.streaming.Subscription` handle.
        """
        item = f"mk{market_id}"

        def _callback(raw: dict[str, str | None]) -> None:
            on_update(MarketUpdate(raw))

        return self.subscribe_raw(
            mode=_MODE_MERGE,
            item=item,
            fields=MARKET_FIELDS,
            on_update=_callback,
            on_error=on_error,
            stream_type="MarketStatistics",
        )

    def subscribe_trades(
        self,
        symbol: str,
        on_update: Callable[[TradeUpdate], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> Subscription:
        """Subscribe to the trade tape for a stock (SecurityTrades stream).

        Delivers every executed trade in COMMAND mode — each callback
        invocation carries one trade event with a ``command`` field
        (``"ADD"``, ``"UPDATE"``, or ``"DELETE"``).

        Args:
            symbol: EGX ticker (e.g. ``"EFIH"``).
            on_update: Called with a :class:`~younit.models.streaming.TradeUpdate`.
            on_error: Optional error callback.

        Returns:
            :class:`~younit.models.streaming.Subscription` handle.
        """
        stock_id = self._symbol_resolver(symbol)
        item = f"ts{stock_id}"

        def _callback(raw: dict[str, str | None]) -> None:
            on_update(TradeUpdate(raw))

        return self.subscribe_raw(
            mode=_MODE_COMMAND,
            item=item,
            fields=TRADE_FIELDS,
            on_update=_callback,
            on_error=on_error,
            stream_type="SecurityTrades",
        )

    def subscribe_orders(
        self,
        on_update: Callable[[OrderUpdate], None],
        on_error: Callable[[Exception], None] | None = None,
        client_account_id: str | None = None,
    ) -> Subscription:
        """Subscribe to live order status updates for the authenticated client.

        Delivers ADD/UPDATE/DELETE events as orders are submitted, filled,
        amended, and cancelled.  This is the recommended alternative to
        polling ``GET /api/v1/orders/{orderId}/info`` after placing a trade.

        Args:
            on_update: Called with an :class:`~younit.models.streaming.OrderUpdate`.
            on_error: Optional error callback.
            client_account_id: The ``profileId`` for the account to subscribe for.
                Confirmed by EFG backend team: ``clientAccountId = profileId``
                (one client may have multiple profiles/sub-accounts).
                Defaults to the cached ``profileId`` from the last
                :meth:`~younit.client.Client.buying_power` or order call,
                falling back to ``trading_id`` if not yet resolved.

        Returns:
            :class:`~younit.models.streaming.Subscription` handle.

        Example::

            sub = client.streaming.subscribe_orders(
                on_update=lambda u: print(
                    f"Order {u.order_number}: {u.status_ui} "
                    f"({u.executed_quantity}/{u.quantity} filled)"
                )
            )
        """
        account_id = client_account_id
        if account_id is None and self._profile_id_getter is not None:
            pid = self._profile_id_getter()
            if pid is not None:
                account_id = str(pid)
        if account_id is None:
            account_id = self._settings.trading_id
        item = f"po{account_id}"

        def _callback(raw: dict[str, str | None]) -> None:
            on_update(OrderUpdate(raw))

        return self.subscribe_raw(
            mode=_MODE_COMMAND,
            item=item,
            fields=ORDER_FIELDS,
            on_update=_callback,
            on_error=on_error,
            stream_type="ActiveOrders",
            data_adapter=self._settings.streaming_adapter_trading,
        )

    def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel an active subscription.

        Args:
            subscription: The :class:`~younit.models.streaming.Subscription`
                returned by a ``subscribe_*`` call. Also accepts a composite
                handle whose ``_ls_subscription`` is a ``list[Subscription]``
                (e.g. from :meth:`~younit.client.Client.stream_top_movers`) —
                each underlying per-symbol subscription is unsubscribed in turn.

        Raises:
            StreamingError: If the unsubscription fails.
        """
        if isinstance(subscription._ls_subscription, list):
            for child in subscription._ls_subscription:
                self.unsubscribe(child)
            return

        with self._lock:
            if self._ls_client is None or subscription._ls_subscription is None:
                return
            try:
                self._ls_client.unsubscribe(subscription._ls_subscription)
                self._active_subs = [s for s in self._active_subs if s is not subscription]
                _log.info(
                    "streaming_unsubscribed",
                    stream_type=subscription.stream_type,
                    item=subscription.item,
                )
            except Exception as exc:
                raise StreamingError(
                    f"Failed to unsubscribe from {subscription.stream_type}: {exc}"
                ) from exc

    def subscribe_raw(
        self,
        mode: str,
        item: str,
        fields: list[str],
        on_update: Callable[[dict[str, str | None]], None],
        on_error: Callable[[Exception], None] | None = None,
        stream_type: str = "raw",
        snapshot: bool = True,
        data_adapter: str | None = None,
    ) -> Subscription:
        """Low-level subscription method.  Directly wraps the Lightstreamer API.

        Use this as an escape hatch if you need to subscribe to a stream
        that is not covered by the named ``subscribe_*`` methods.

        Args:
            mode: Lightstreamer subscription mode: ``"MERGE"`` or ``"COMMAND"``.
            item: Lightstreamer item name (e.g. ``"sy12345"``).
            fields: List of field names to request.
            on_update: Callback invoked with a ``dict[str, str | None]`` of
                changed field values.
            on_error: Optional callback invoked on subscription-level errors.
            stream_type: Human-readable label stored on the Subscription handle.
            snapshot: If True, request an initial snapshot (default True).

        Returns:
            :class:`~younit.models.streaming.Subscription` handle.

        Raises:
            ConnectionFailed: If the connection cannot be established.
            SubscriptionFailed: If the server rejects the subscription.
        """
        if not self._connected:
            self.connect()

        sub_handle = Subscription(
            stream_type=stream_type,
            item=item,
            on_update=on_update,
            on_error=on_error,
        )

        try:
            ls_sub = self._make_ls_subscription(
                mode=mode,
                item=item,
                fields=fields,
                on_update=on_update,
                on_error=on_error,
                snapshot=snapshot,
                data_adapter=data_adapter or self._settings.streaming_adapter,
            )
            sub_handle._ls_subscription = ls_sub
            with self._lock:
                self._ls_client.subscribe(ls_sub)
                self._active_subs.append(sub_handle)
        except SubscriptionFailed:
            raise
        except Exception as exc:
            raise SubscriptionFailed(
                f"Failed to subscribe to {stream_type} item {item!r}: {exc}"
            ) from exc

        _log.info(
            "streaming_subscribed",
            stream_type=stream_type,
            item=item,
            mode=mode,
        )
        return sub_handle

    # ------------------------------------------------------------------
    # Private implementation
    # ------------------------------------------------------------------

    def _do_connect(self) -> None:
        """Create and connect a LightstreamerClient (called under _lock)."""
        try:
            from lightstreamer.client import LightstreamerClient  # type: ignore[import-untyped]
        except ImportError as exc:
            raise StreamingError(
                "The 'lightstreamer-client-lib' package is required for streaming. "
                "Install it with: pip install lightstreamer-client-lib"
            ) from exc

        token = self._token_getter()
        ls_client = LightstreamerClient(
            _STREAMING_URL,
            self._settings.streaming_adapter,
        )
        ls_client.connectionDetails.setUser(self._settings.trading_id)
        ls_client.connectionDetails.setPassword(token)

        # Register connection status listener
        ls_client.addListener(_ConnectionListener(self))

        _log.info(
            "streaming_connecting",
            url=_STREAMING_URL,
            adapter=self._settings.streaming_adapter,
        )
        ls_client.connect()
        self._ls_client = ls_client

    def _make_ls_subscription(
        self,
        *,
        mode: str,
        item: str,
        fields: list[str],
        on_update: Callable[[dict[str, str | None]], None],
        on_error: Callable[[Exception], None] | None,
        snapshot: bool,
        data_adapter: str | None = None,
    ) -> Any:  # noqa: ANN401 — wrapping dynamic Lightstreamer subscription object
        """Build a Lightstreamer Subscription object with the given parameters."""
        try:
            from lightstreamer.client import Subscription as LSSubscription
        except ImportError as exc:
            raise StreamingError(
                "The 'lightstreamer-client-lib' package is required for streaming. "
                "Install it with: pip install lightstreamer-client-lib"
            ) from exc

        ls_sub = LSSubscription(mode, [item], fields)
        ls_sub.setDataAdapter(data_adapter or self._settings.streaming_adapter)
        ls_sub.setRequestedSnapshot("yes" if snapshot else "no")
        ls_sub.addListener(
            _SubscriptionListener(
                on_update=on_update,
                on_error=on_error,
                item=item,
                fields=fields,
                stream_type="",  # filled from the Subscription handle
            )
        )
        return ls_sub

    def _on_status_change(self, status: str) -> None:
        """Called by the Lightstreamer listener on connection status change."""
        _log.info("streaming_status", status=status)
        connected = status.startswith("CONNECTED")
        if connected and not self._connected:
            self._connected = True
            self._connect_event.set()
        elif not connected and self._connected:
            self._connected = False

    def _on_server_error(self, code: int, message: str) -> None:
        """Called by the Lightstreamer listener on server-level errors."""
        _log.error("streaming_server_error", code=code, message=message)
        self._connected = False
        self._connect_event.set()  # unblock connect() waiter


# ---------------------------------------------------------------------------
# Internal Lightstreamer listener adapters
# ---------------------------------------------------------------------------


class _ConnectionListener:
    """Adapts Lightstreamer connection events to StreamingClient methods."""

    def __init__(self, streaming_client: StreamingClient) -> None:
        self._client = streaming_client

    def onStatusChange(self, status: str) -> None:  # noqa: N802
        self._client._on_status_change(status)

    def onServerError(self, code: int, message: str) -> None:  # noqa: N802
        self._client._on_server_error(code, message)

    def onPropertyChange(self, property_name: str) -> None:  # noqa: N802
        pass  # Not used

    def onListenEnd(self) -> None:  # noqa: N802
        pass  # Not used

    def onListenStart(self) -> None:  # noqa: N802
        pass  # Not used


class _SubscriptionListener:
    """Adapts Lightstreamer item updates to the user's on_update callback."""

    def __init__(
        self,
        *,
        on_update: Callable[[dict[str, str | None]], None],
        on_error: Callable[[Exception], None] | None,
        item: str,
        fields: list[str],
        stream_type: str,
    ) -> None:
        self._on_update = on_update
        self._on_error = on_error
        self._item = item
        self._fields = fields
        self._stream_type = stream_type
        self._log = get_logger(__name__)

    def onItemUpdate(self, update: Any) -> None:  # noqa: N802, ANN401
        """Convert a Lightstreamer ItemUpdate to a dict and call the user callback."""
        try:
            raw: dict[str, str | None] = {}
            for field in self._fields:
                raw[field] = update.getValue(field)
            self._on_update(raw)
        except Exception as exc:
            self._log.error(
                "streaming_callback_error",
                item=self._item,
                error=str(exc),
            )
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except Exception:  # noqa: S110 — error callback must never crash the update loop
                    pass  # Error callback itself failed — swallow silently

    def onSubscription(self) -> None:  # noqa: N802
        self._log.debug("subscription_active", item=self._item)

    def onUnsubscription(self) -> None:  # noqa: N802
        self._log.debug("subscription_inactive", item=self._item)

    def onSubscriptionError(self, code: int, message: str) -> None:  # noqa: N802
        """Raise SubscriptionFailed and call the error callback if provided."""
        exc = SubscriptionFailed(
            f"Subscription error for item {self._item!r}: [{code}] {message}",
            code=code,
            error_message=message,
        )
        self._log.error(
            "subscription_error",
            item=self._item,
            code=code,
            message=message,
        )
        if self._on_error is not None:
            try:
                self._on_error(exc)
            except Exception:  # noqa: S110 — error callback must never suppress the SubscriptionFailed re-raise
                pass
        # Do NOT silently swallow — re-raise so the client knows
        raise exc

    def onListenEnd(self) -> None:  # noqa: N802
        pass

    def onListenStart(self) -> None:  # noqa: N802
        pass

    def onEndOfSnapshot(self, item_name: str, item_pos: int) -> None:  # noqa: N802
        self._log.debug("snapshot_complete", item=item_name)

    def onClearSnapshot(self, item_name: str, item_pos: int) -> None:  # noqa: N802
        pass

    def onLostUpdates(self, item_name: str, item_pos: int, lost: int) -> None:  # noqa: N802
        self._log.warning(
            "streaming_lost_updates",
            item=item_name,
            lost_count=lost,
        )
