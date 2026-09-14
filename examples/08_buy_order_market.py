"""Example 08 — Place a market buy order.

⚠️  WARNING: This places a REAL order using real funds and real money.

A market order executes immediately at the best available price — there's
no price to set or validate, unlike a limit order (see example 09).

This example demonstrates:
- Checking buying power before ordering
- Placing a market buy order
- Resolving the real order_id immediately (confirm=True is now the default)
- Handling order errors

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

from younit import Client
from younit.exceptions import APIError, InsufficientFunds, OrderRejected

SYMBOL = "CRST"
QUANTITY = 1  # shares

with Client() as client:
    quote = client.quote(SYMBOL)
    print(f"Placing MARKET BUY: {QUANTITY} x {SYMBOL} (last price: {quote.last:.2f} EGP)")

    try:
        order = client.buy_market(
            symbol=SYMBOL,
            qty=QUANTITY,
        )
        print(f"OK: Order submitted — orderId: {order.order_id}")
        print(f"    status: {order.status}")
        # status_text is the real, populated status (status is reserved for
        # unconfirmed numeric codes and is currently always None)
        print(f"    status_text: {order.status_text}")

    except InsufficientFunds as exc:
        print(f"FAILED: Insufficient funds: {exc}")

    except OrderRejected as exc:
        print(f"FAILED: Order rejected by exchange: {exc}")

    except APIError as exc:
        # The exchange can also reject an order with an HTTP 400, e.g. a
        # compliance suspension on the symbol/account ("Order Suspend Compliance").
        print(f"FAILED: Order request failed ({exc.status_code}): {exc.message}")
        