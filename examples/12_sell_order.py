"""Example 12 — Close (sell) an existing position.

⚠️  WARNING: This places a REAL sell order using real shares.

This example demonstrates:
- Fetching your current position for a symbol
- Selling your full sellable quantity to close it out
- Handling the case where you hold nothing to sell

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
- You must already hold a position in SYMBOL (see example 08/09 to open one)
"""

from younit import Client
from younit.exceptions import APIError, InsufficientFunds, InvalidOrder, OrderRejected

SYMBOL = "DEIN"

with Client() as client:
    pos = client.position(SYMBOL)

    if pos is None or pos.quantity <= 0:
        raise SystemExit(f"No position found for {SYMBOL}. Nothing to close.")

    print(f"Current {SYMBOL} position:")
    print(f"  Quantity held:       {pos.quantity}")
    print(f"  Available to sell:   {pos.qty_valid_for_sale}")
    print(f"  Average buy price:   {pos.average_price:.4f} EGP")
    print(f"  Current market price:{pos.market_price:.4f} EGP")
    print(f"  Unrealized P&L:      {pos.unrealized_pnl:+.2f} EGP ({pos.unrealized_pnl_pct:+.2f}%)")

    qty_to_sell = pos.qty_valid_for_sale
    print(f"\nPlacing MARKET SELL: {qty_to_sell} x {SYMBOL}")

    quote = client.quote(SYMBOL)
    limit_price = round(quote.min_price*1.01, 1)  # 1% below market

    try:
        order = client.sell_market(
            symbol=SYMBOL,
            qty=1,               # expire_date is now auto-supplied
            settlement="t0",     # same-day settlement close
        )

        # order = client.sell_limit(
        #     symbol=SYMBOL,
        #     qty=1,
        #     price=limit_price,
        #     settlement="t0",
        # )

        print(f"OK: Order submitted — orderId: {order.order_id}")
        print(f"    status: {order.status}")

    except InsufficientFunds as exc:
        print(f"FAILED: Insufficient funds: {exc}")
    except InvalidOrder as exc:
        print(f"FAILED: Invalid order parameters: {exc}")
    except OrderRejected as exc:
        print(f"FAILED: Order rejected by exchange: {exc}")
    except APIError as exc:
        print(f"FAILED: Order request failed ({exc.status_code}): {exc.message}")
