"""Example — Sell (redeem) fund units.

⚠️  WARNING: This places a REAL fund sell order using real holdings.

This example demonstrates:
- Finding a fund position you actually hold (via fund_positions())
- Selling units of that fund via sell_fund()

Note: fund holdings from a same-day buy typically aren't sellable
until settlement completes (end of day) — same T+ settlement pattern
observed for stocks. Run this a day after buying, not immediately.

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
- You must hold units in at least one fund (see the fund buy example)
"""

from younit import Client
from younit.exceptions import APIError, InvalidOrder, OrderRejected

with Client() as client:
    fund_positions = client.fund_positions()
    held = [fp for fp in fund_positions if fp.qty_valid_for_sale > 0]

    if not held:
        raise SystemExit("No sellable fund positions found. Nothing to sell.")

    fp = held[0]
    quantity = fp.qty_valid_for_sale
    price = fp.market_price

    print(f"Selling fund [{fp.fund_id}] {fp.name}")
    print(f"  Quantity: {quantity}")
    print(f"  Price (NAV): {price:.4f} {fp.currency}")

    try:
        order = client.sell_fund(
            fund_id=fp.fund_id,
            qty=quantity,
            price=price,
        )
        print(f"OK: Order submitted — orderId: {order.order_id}  fundId: {order.fund_id}")

    except InvalidOrder as exc:
        print(f"FAILED: Invalid order parameters: {exc}")
    except OrderRejected as exc:
        print(f"FAILED: Order rejected: {exc}")
    except APIError as exc:
        print(f"FAILED: Order request failed ({exc.status_code}): {exc.message}")
