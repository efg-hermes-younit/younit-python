"""Example 04 — Market movers: top gainers, losers, trending, search.

This example demonstrates:
- Top gainers and losers by percentage change
- Trending stocks
- Local symbol search

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from younit import Client

with Client() as client:
    # Top gainers today on EGX
    # Note: markets may be closed — lists will be empty outside trading hours
    movers = client.get_top_movers(limit=50)

    print("=== Top Gainers ===")
    for m in movers[:5]:
        print(f"  {m.symbol:<8} last={m.last:.2f}  change={m.change:+.2f}  ({m.change_pct:+.2f}%)")

    print()

    print("\n=== Top Losers ===")
    for m in movers[-5:]:
        print(f"  {m.symbol:<8} last={m.last:.2f}  change={m.change:+.2f}  ({m.change_pct:+.2f}%)")

    print()

    # Trending stocks
    print("=== Trending Stocks ===")
    for stock in client.trending_stocks()[:5]:
        print(
            f"  [{stock.stock_id}] {stock.symbol:<8} {stock.short_name:<22}"
            f"  reuters={stock.reuters_code}  ccy={stock.currency}"
        )

    print()

    # Search for stocks by ticker substring (local search, no API call)
    print("=== Search: 'COM' ===")
    results = client.search_stocks("COM")
    for stock in results[:5]:
        print(f"  {stock.symbol} (stockId: {stock.stock_id})")
