"""Example — Buy fund units.

⚠️  WARNING: This places a REAL fund order using real funds.

This example demonstrates:
- Listing available funds
- Buying units via buy_fund()

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from younit import Client
from younit.exceptions import APIError, InvalidOrder, OrderRejected
from younit.models.funds import Fund


with Client() as client:
    funds = client.list_funds()
    print(f"=== Investment Funds ({len(funds)} available) ===")
    Fund.print_table(funds)  # show first 5

    fund = funds[3]
    quantity = 2
    price = fund.nav

    print(f"Buying fund [{fund.fund_id}] {fund.name}")
    print(f"  Quantity: {quantity}")
    print(f"  Price (NAV): {price:.4f} {fund.currency}")

    try:
        order = client.buy_fund(
            fund_id=fund.fund_id,
            qty=quantity,
            price=price,
            is_ipo_fund=fund.is_ipo,
        )
        print(f"OK: Order submitted — orderId: {order.order_id}  fundId: {order.fund_id}")

    except InvalidOrder as exc:
        print(f"FAILED: Invalid order parameters: {exc}")
    except OrderRejected as exc:
        print(f"FAILED: Order rejected: {exc}")
    except APIError as exc:
        print(f"FAILED: Order request failed ({exc.status_code}): {exc.message}")
