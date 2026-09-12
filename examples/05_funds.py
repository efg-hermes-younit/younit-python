"""Example 05 — List available investment funds and performance data.

This example demonstrates:
- Listing all available investment funds
- Fetching fund performance chart data

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

from younit import Client
from younit.models.funds import Fund

with Client() as client:
    # List all investment funds available on EGX
    funds = client.list_funds()
    print(f"=== Investment Funds ({len(funds)} available) ===")
    Fund.print_table(funds)  # show first 5

    if not funds:
        print("  No funds returned.")
    else:
        # Fetch performance data for the first fund
        # NOTE: filter_type's full value mapping is not currently documented
        # by the API. filter_type=3 is used here as an example value only —
        # do not treat this as a confirmed "1Y" or any other specific meaning.
        first_fund = funds[0]
        print(f"\n=== Performance: {first_fund.name} ===")
        perf = client.fund_performance(first_fund.fund_id, filter_type=3)
        print(f"  Fund ID:     {perf.fund_id}")
        print(f"  Filter type: {perf.filter_type}")
        print(f"  Data points: {len(perf.chart_data)}")
        if perf.chart_data:
            first_dp = perf.chart_data[0]
            last_dp = perf.chart_data[-1]
            print(f"  From: {first_dp.date}  price={first_dp.value}  ccy={first_dp.currency}")
            print(f"  To:   {last_dp.date}   price={last_dp.value}  ccy={last_dp.currency}")
