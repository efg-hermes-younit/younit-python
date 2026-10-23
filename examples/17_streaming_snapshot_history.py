"""Example 13 — Stream every price tick for a single stock (not just the latest).

subscribe_quote() delivers one callback per update. This example keeps
every tick received during the streaming window, rather than only the
most recent snapshot — useful for logging, charting, or replaying the
full sequence of price changes.

See example 12 for subscribing to multiple symbols concurrently on one
connection; this example focuses on a single symbol in more depth.

Prerequisites:
- pip install lightstreamer-client-lib
- Set TRADING_ID and API_KEY in your environment or .env
"""

import queue
import time

from younit import Client, SymbolUpdate

SYMBOL = "HRHO"

# How many seconds to stream before exiting
STREAM_SECONDS = 10

with Client() as client:
    updates: queue.Queue[SymbolUpdate] = queue.Queue()

    def on_update(update: SymbolUpdate) -> None:
        updates.put(update)

    def on_error(exc: Exception) -> None:
        print(f"[ERROR] Streaming error: {exc}")

    print("Connecting to streaming server...")
    client.streaming.connect()
    print(f"Connected. Subscribing to {SYMBOL} quote stream...")

    sub = client.streaming.subscribe_quote(
        SYMBOL,
        on_update=on_update,
        on_error=on_error,
    )

    print(f"Subscribed. Streaming for {STREAM_SECONDS}s — press Ctrl+C to stop early.\n")

    try:
        time.sleep(STREAM_SECONDS)
    except KeyboardInterrupt:
        pass

    print(f"Received {updates.qsize()} update(s). Processing in order:\n")

    if updates.empty():
        print(
            f"No updates received for {SYMBOL} — market may be closed, "
            "or check the streaming connection."
        )
    else:
        count = 0
        while not updates.empty():
            u = updates.get()
            count += 1
            print(f"  [{count}] last={u.last}  bid={u.bid}  ask={u.ask}  vol={u.volume}")

    print("\nUnsubscribing...")
    client.streaming.unsubscribe(sub)
    print("Done.")
