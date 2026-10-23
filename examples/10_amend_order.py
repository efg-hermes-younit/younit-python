"""Example 10 — Amend (modify) an open order.

⚠️  WARNING: This places AND modifies a REAL order using real funds.

This example places a limit order deliberately far below market (so it
stays open rather than filling immediately), then amends its price and
quantity. amend_order() returns a bool (True if the amendment was
accepted) — it does not return the updated order, so get_order() is
called afterward to see the new price/quantity/status.

This example demonstrates:
- Placing a limit order that stays open (for amending)
- Amending price and quantity on an open order
- Checking the result via get_order()

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from younit import Client
from younit.exceptions import APIError, BadRequest, InsufficientFunds, NotFound, OrderRejected

SYMBOL = "FWRY"
QUANTITY = 1

with Client() as client:
    # ------------------------------------------------------------------
    # Step 1: Place a limit order deliberately far from market (5% below)
    # so it stays open rather than filling immediately, giving us
    # something to amend.
    # ------------------------------------------------------------------
    quote = client.quote(SYMBOL)
    initial_price = round(quote.last * 0.95, 1)

    print(f"Placing LIMIT BUY: {QUANTITY} x {SYMBOL} @ {initial_price:.2f} EGP (to amend next)")

    try:
        order = client.buy_limit(symbol=SYMBOL, qty=QUANTITY, price=initial_price)
    except (InsufficientFunds, OrderRejected, APIError) as exc:
        raise SystemExit(f"FAILED: Could not place the initial order: {exc}") from None

    if order.order_id is None:
        raise SystemExit(
            "FAILED: Order was placed but order_id could not be confirmed in time. "
            "Check your open orders manually before retrying this example."
        )

    print(f"OK: Order placed — orderId: {order.order_id}\n")

    # ------------------------------------------------------------------
    # Step 2: Amend the order's price and quantity
    # ------------------------------------------------------------------
    profile_id = client.buying_power(SYMBOL).profile_id
    new_price = round(quote.last * 0.97, 2)  # move closer to market: 1% below
    new_qty = 2

    print(f"Amending order {order.order_id}:")
    print(f"  New quantity: {new_qty}")
    print(f"  New price:    {new_price:.2f} EGP")

    try:
        amended = client.amend_order(
            order.order_id,
            profile_id=profile_id,
            qty=new_qty,
            price=new_price,
        )
        if amended:
            print(f"OK: Order {order.order_id} amended successfully.")
            updated = client.get_order(order.order_id)
            print(f"    Status: {updated.status}")
        else:
            print(f"FAILED: Order {order.order_id} amendment was not accepted.")

    except NotFound:
        print(f"FAILED: Order {order.order_id} not found.")

    except BadRequest as exc:
        print(f"FAILED: Bad request: {exc}")
