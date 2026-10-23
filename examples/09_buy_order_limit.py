"""Example 09 — Place a limit buy order.

⚠️  WARNING: This places a REAL order using real funds and real money.

A limit order only executes at your specified price or better. The SDK
validates the limit price against the stock's allowed min/max range
before submitting (see place_order() — raises InvalidOrder if outside range).

This example demonstrates:
- Checking the current quote to choose a sensible limit price
- Placing a limit buy order
- Resolving the real order_id immediately (confirm=True is now the default)
- Handling order errors, including InvalidOrder for out-of-range prices

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from younit import Client
from younit.exceptions import APIError, InsufficientFunds, InvalidOrder, OrderRejected

SYMBOL = "EAST"
QUANTITY = 1  # shares

with Client() as client:
    quote = client.quote(SYMBOL)
    limit_price = round(quote.last * 0.95, 1)  # 1% below market

    print(f"Placing LIMIT BUY: {QUANTITY} x {SYMBOL} @ {limit_price:.2f} EGP")
    print(
        f"  (Market price: {quote.last:.2f}, "
        f"allowed range: {quote.min_price:.2f}-{quote.max_price:.2f})"
    )

    try:
        order = client.buy_limit(
            symbol=SYMBOL,
            qty=QUANTITY,
            price=limit_price,
        )
        print(f"OK: Order submitted — orderId: {order.order_id}")
        print(f"    status: {order.status}")
        # status_text is the real, populated status (status is reserved for
        # unconfirmed numeric codes and is currently always None)
        print(f"    status_text: {order.status_text}")

    except InsufficientFunds as exc:
        print(f"FAILED: Insufficient funds: {exc}")

    except InvalidOrder as exc:
        print(f"FAILED: Invalid order parameters: {exc}")

    except OrderRejected as exc:
        print(f"FAILED: Order rejected by exchange: {exc}")

    except APIError as exc:
        print(f"FAILED: Order request failed ({exc.status_code}): {exc.message}")
