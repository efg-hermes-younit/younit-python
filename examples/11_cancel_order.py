"""Example 11 — Cancel an open order.

⚠️  WARNING: This places AND cancels a REAL order using real funds.

This example places a limit order deliberately far below market (so it
stays open rather than filling immediately), then cancels it.

This example demonstrates:
- Placing a limit order that stays open (for cancelling)
- Cancelling an open order
- Confirming the cancellation via get_order()

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from time import sleep

from younit import Client
from younit.exceptions import APIError, BadRequest, InsufficientFunds, NotFound, OrderRejected

SYMBOL = "FWRY"
QUANTITY = 1

with Client() as client:
    # ------------------------------------------------------------------
    # Step 1: Place a limit order deliberately far from market (5% below)
    # so it stays open rather than filling immediately, giving us
    # something to cancel.
    # ------------------------------------------------------------------
    quote = client.quote(SYMBOL)
    limit_price = round(quote.last * 0.95, 1)

    print(f"Placing LIMIT BUY: {QUANTITY} x {SYMBOL} @ {limit_price:.2f} EGP (to cancel next)")

    try:
        order = client.buy_limit(symbol=SYMBOL, qty=QUANTITY, price=limit_price)
    except (InsufficientFunds, OrderRejected, APIError) as exc:
        raise SystemExit(f"FAILED: Could not place the initial order: {exc}") from None

    if order.order_id is None:
        raise SystemExit(
            "FAILED: Order was placed but order_id could not be confirmed in time. "
            "Check your open orders manually before retrying this example."
        )

    print(f"OK: Order placed — orderId: {order.order_id}\n")

    # ------------------------------------------------------------------
    # Step 2: Cancel the order
    # ------------------------------------------------------------------
    print(f"Cancelling order {order.order_id}...")
    sleep(5)  # brief pause to ensure the order is registered before attempting cancellation

    try:
        cancelled = client.cancel_order(order.order_id)
        if cancelled:
            print(f"OK: Order {order.order_id} cancelled successfully.")
            try:
                updated = client.get_order(order.order_id)
                print(f"    Status: {updated.status}")
            except APIError as exc:
                print(f"    (Could not fetch updated status: {exc})")
        else:
            print(
                f"FAILED: Order {order.order_id} cancel returned false (may already be executed)."
            )

    except NotFound:
        print(f"FAILED: Order {order.order_id} not found.")

    except BadRequest as exc:
        print(f"FAILED: Bad request: {exc}")
