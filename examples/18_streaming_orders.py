"""Example 14 — Place an order and watch its lifecycle via the ActiveOrders stream.

⚠️  WARNING: This places a REAL order using real funds.

This example demonstrates:
- Subscribing to the ActiveOrders stream BEFORE placing an order
- Placing a limit buy order (far below market so it stays open)
- Receiving real-time status updates (submitted -> accepted -> filled/cancelled)
- Cancelling the order after it's confirmed active
- Unsubscribing cleanly

The ActiveOrders stream is the recommended way to see real-time order
status (submitted -> accepted -> filled/cancelled); GET /api/v1/orders/
{orderId}/info and place_order()'s confirm=True (now the default) resolve
order_id immediately but never return real status — use this stream (or
list_orders()) for that.

Prerequisites:
- pip install lightstreamer-client-lib
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

import time

from younit import Client, OrderUpdate

SYMBOL = "CRST"
STREAM_SECONDS = 120  # watch for this long after placing


def on_order_update(update: OrderUpdate) -> None:
    print('Subscriped to order update:...')
    price = f"{update.price:.2f} EGP" if update.price else "MARKET"
    print(
        f"  [{update.command:>6}] order={update.order_number}  "
        f"status={update.status_ui or update.status}  "
        f"filled={update.executed_quantity}/{update.quantity}  {price}"
    )


def on_error(exc: Exception) -> None:
    print(f"[STREAM ERROR] {exc}")


with Client() as client:
    print("Subscribing to the ActiveOrders stream...")
    order_sub = client.streaming.subscribe_orders(on_update=on_order_update, on_error=on_error)
    print("Subscribed — waiting 1s for initial snapshot...\n")
    time.sleep(1)

    quote = client.quote(SYMBOL)
    limit_price = round(quote.last * 0.95, 1)
    # limit_price = round(quote.max_price*0.995, 1)
    print(f"Placing LIMIT BUY: 1 x {SYMBOL} @ {limit_price:.2f} EGP (market {quote.last:.2f})\n")
    order = client.buy_market(SYMBOL, qty=1)
    print(f"Order placed — orderId: {order.order_id}\n")

    print(f"Watching stream for {STREAM_SECONDS}s (Ctrl-C to stop early)...\n")
    try:
        time.sleep(STREAM_SECONDS)
    except KeyboardInterrupt:
        pass

    client.streaming.unsubscribe(order_sub)
    print("Done.")
