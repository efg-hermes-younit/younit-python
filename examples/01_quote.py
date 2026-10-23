"""Example 01 — Get a live quote for an EGX stock.

This example demonstrates:
- How to create a Client from environment variables
- How to fetch a current price snapshot

The quote() call returns a Quote object (see models/market_data.py for
the full field list and types) — the fields used below are a subset.

Prerequisites:
- Set TRADING_ID and API_KEY in your environment or .env
"""

from younit import Client

# All credentials are loaded from environment variables.
# Never hardcode credentials in scripts.

with Client() as client:
    # Get the current price snapshot for HRHO (EFG Hermes Holding)
    quote = client.quote("HRHO")

    print(f"Ticker:       {quote.symbol}")
    print(f"Last price:   {quote.last:.2f} EGP")
    print(f"Price range:  {quote.min_price:.2f} - {quote.max_price:.2f} EGP")
    print(f"Intraday:     {quote.is_intraday}")
    print(f"T+1:          {quote.is_tplus1}")

    # Market status: the open/closed mapping is empirically derived from live
    # observation, pending official confirmation from the backend team.
    print(f"\nMarket status: {client.market_status()}")
