"""Example 07 — Get buying power and profileId for a stock.

buying_power() is step 1 of the 3-call order placement flow:
  1. buying_power()  → returns profileId (required for every order)
  2. quote()         → validate limit price is within the allowed range
  3. place_order()   → submit the order

This example demonstrates:
- How to fetch buying power for a stock
- Where profileId comes from and why it's required before placing an order

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

from younit import Client

with Client() as client:
    bp = client.buying_power("HRHO")

    print("=== Buying Power for HRHO ===")
    print(f"  profile_id:    {bp.profile_id}  (required in the order request body)")
    print(f"  profile_name:  {bp.profile_name}")
    print(f"  buying_power:  {bp.buying_power:.2f} EGP  (pre-formatted: {bp.buying_power_str})")
    print(f"  shares_held:   {bp.certificates_quantity_held}")

    # The buy()/sell() convenience methods call buying_power() automatically —
    # you don't need to call it yourself before using them. Use place_order()
    # directly only if you need to supply a pre-fetched profileId, or if
    # you've already retrieved it earlier in your own workflow.
    