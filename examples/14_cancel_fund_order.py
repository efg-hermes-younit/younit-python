"""Example — Cancel a fund order.

⚠️  WARNING: This places AND cancels a REAL fund order using real funds.

This example demonstrates:
- Placing a fund buy order
- Cancelling it via cancel_fund_order() (the correct, dedicated
  endpoint for fund orders — not cancel_order(), which is for stocks,
  though cancel_order() has separately been confirmed to also work
  against fund orders as an observed backend behavior)

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

from younit import Client
from younit.exceptions import APIError, InvalidOrder, OrderRejected
from younit.models.funds import Fund


with Client() as client:
    funds = client.list_funds()
    print(f"=== Investment Funds ({len(funds)} available) ===")
    Fund.print_table(funds)  # show first 5

    fund = funds[0]
    quantity = 1
    price = fund.nav

    print(f"Placing fund BUY: [{fund.fund_id}] {fund.name} x{quantity} @ {price:.4f} {fund.currency}")

    try:
        order = client.buy_fund(
            fund_id=fund.fund_id,
            qty=quantity,
            price=price,
            is_ipo_fund=fund.is_ipo,
        )
    except (InvalidOrder, OrderRejected, APIError) as exc:
        raise SystemExit(f"FAILED: Could not place the fund order: {exc}")

    print(f"OK: Order placed — orderId: {order.order_id}  fundId: {order.fund_id}\n")

    print(f"Cancelling fund order {order.order_id}...")
    try:
        cancelled = client.cancel_fund_order(order.order_id)
        if cancelled:
            print(f"OK: Fund order {order.order_id} cancelled successfully.")
        else:
            print(f"FAILED: Fund order {order.order_id} cancel returned false.")
    except APIError as exc:
        print(f"FAILED: Cancel request failed: {exc}")
