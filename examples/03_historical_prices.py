"""Example 03 — Historical charting data feed.

This example demonstrates:
- Fetching historical OHLCV candles for a security
- Using DateFrom / DateTo to specify an explicit date range
- Using all four ChartPeriod values (Day, Week, Month, Year)
- Printing a simple price table and basic stats

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

from datetime import date, timedelta

from younit import ChartPeriod, Client
from younit.models.market_data import HistoricalCandle

SYMBOL = "HRHO"  # EFG Hermes Holding

with Client() as client:
    # ------------------------------------------------------------------
    # Fetch candles for an explicit date range (last 30 days from today)
    # ------------------------------------------------------------------
    date_to = date.today()
    date_from = date_to - timedelta(days=30)

    # date_from = date(2018, 7, 20)
    # date_to = date(2018, 9, 14)

    print(f"=== {SYMBOL} — Daily candles {date_from} → {date_to} ===")
    candles = client.historical_prices(
        SYMBOL,
        period=ChartPeriod.DAY,
        date_from=str(date_from),
        date_to=str(date_to),
    )

    if not candles:
        print("  No data returned.")
    else:
        HistoricalCandle.print_table(candles)

        closes = [c.close for c in candles if c.close]
        if closes:
            print(f"\n  Period high:  {max(c.high for c in candles):.2f} EGP")
            print(f"  Period low:   {min(c.low  for c in candles):.2f} EGP")
            print(f"  First close:  {closes[0]:.2f} EGP")
            print(f"  Last close:   {closes[-1]:.2f} EGP")
            change_pct = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0
            print(f"  Period return: {change_pct:+.2f}%")

