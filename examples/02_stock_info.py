"""Example 02 — Get full stock details (price, limits, T+1, intraday).

This example demonstrates:
- Fetching complete trading information for a stock
- Understanding price limits for order validation
- Filtering the full stock universe by instrument class or same-day
  trading eligibility

Only the Egyptian market (EGX) is currently supported, so market_id
defaults to 1 and doesn't need to be passed explicitly.

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from younit import Client

with Client() as client:
    stocks = client.list_stocks()
    print(f"=== Stocks on EGX ({len(stocks)} total, first 5) ===")
    for s in stocks[:5]:
        print(
            f"  [{s.stock_id}] {s.symbol:<8} {s.short_name:<22}"
            f"  reuters={s.reuters_code:<10}  ccy={s.currency}  auction={s.is_auction}"
        )
    print()

    # stock_info() is an alias for quote() — returns the same data
    info = client.stock_info("HRHO")  # EFG Hermes Holding

    print("=== Stock Trading Info ===")
    print(f"Symbol:           {info.symbol}")
    print(f"Name:             {info.name}")
    print(f"Last price:       {info.last:.2f} EGP")
    print(f"Min order price:  {info.min_price:.2f} EGP  (price floor for limit orders)")
    print(f"Max order price:  {info.max_price:.2f} EGP  (price ceiling for limit orders)")
    print(f"Intraday (T+0):   {info.is_intraday}")
    print(f"T+1 settlement:   {info.is_tplus1}")

    # This info is used internally by buy()/sell() to validate limit order
    # prices before submitting them to the exchange.
    print()

    # list_by_class()/list_same_day_eligible()/list_otc() are thin,
    # in-memory filters over list_stocks() — no extra API calls.
    tbills = client.list_by_class("LocalSecurity_IN")
    print(f"=== LocalSecurity_IN ({len(tbills)} total) ===")

    same_day = client.list_same_day_eligible()
    print(f"=== Same-day (T+0) eligible stocks ({len(same_day)} total) ===")

    otc = client.list_otc()
    print(f"=== OTC stocks ({len(otc)} total) ===")
