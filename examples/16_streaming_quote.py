"""Example 12 — Subscribe to live price updates for multiple stocks.

This example demonstrates:
- How to connect to the real-time streaming feed
- How one connection supports multiple concurrent symbol subscriptions
  (connect once, subscribe many — you don't need a separate Client per symbol)
- How to receive live bid/ask, last price, and volume updates per symbol
- How to cleanly unsubscribe and disconnect

Real-time data is delivered via Lightstreamer (not WebSocket).
Callbacks fire on Lightstreamer's background thread.

Prerequisites:
- pip install lightstreamer-client-lib
- Set TRADING_ID and API_KEY in your environment or .env
"""

import time

from younit import Client, SymbolUpdate

SYMBOLS = ["VLMRA"]

# How many seconds to stream before exiting
STREAM_SECONDS = 5 * 2

with Client() as client:
    latest: dict[str, SymbolUpdate] = {}

    def make_on_update(symbol: str):
        def on_update(update: SymbolUpdate) -> None:
            latest[symbol] = update
            print(f"Received update for {symbol}: {update}")

        return on_update

    def on_error(exc: Exception) -> None:
        print(f"[ERROR] Streaming error: {exc}")

    print("Connecting to streaming server...")
    client.streaming.connect()

    subs = []
    for symbol in SYMBOLS:
        print(f"Subscribing to {symbol} quote stream...")
        sub = client.streaming.subscribe_quote(
            symbol,
            on_update=make_on_update(symbol),
            on_error=on_error,
        )
        subs.append(sub)

    print(
        f"\nSubscribed to {len(SYMBOLS)} symbols. Streaming for {STREAM_SECONDS}s"
        " - press Ctrl+C to stop early.\n"
    )

    try:
        print("Streaming...")
        time.sleep(STREAM_SECONDS)
    except KeyboardInterrupt:
        pass

    for symbol in SYMBOLS:
        update = latest.get(symbol)
        if update is None:
            print(
                f"{symbol}: No updates received - market may be closed, "
                "or check the streaming connection."
            )
            continue
        print(f"Latest snapshot for {symbol}:")
        print(f"  last      = {update.last}")
        print(f"  bid / ask = {update.bid} / {update.ask}")
        print(f"  volume    = {update.volume}")
        print(f"  change    = {update.change}  ({update.change_pct}%)")
        print(f"  high/low  = {update.high} / {update.low}")
        print(f"  status    = {update.status}")
        print(f"  last_updated = {update.last_updated!r}")
        print()

    print("Unsubscribing...")
    for sub in subs:
        client.streaming.unsubscribe(sub)
    print("Done.")
