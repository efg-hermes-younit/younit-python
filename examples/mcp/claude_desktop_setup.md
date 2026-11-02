# Claude Desktop Configuration for the younit Trading MCP Server

## Quick Start

Add this block to your Claude Desktop configuration file.

**macOS / Linux:** `~/.config/claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "younit": {
      "command": "younit-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "TRADING_ID": "your-trading-id",
        "API_KEY": "your-api-key",
        "EFG_MCP_READONLY": "true",
        "EFG_MCP_MAX_ORDER_VALUE_EGP": "1000",
        "EFG_MCP_MAX_DAILY_ORDERS": "10"
      }
    }
  }
}
```

`younit-mcp` is the console script registered by this package (equivalent
to `python examples/mcp/server.py`, or `python -m younit.mcp_server.server`
directly).

## Safety Controls

Set these in the `env` block above, in the environment, or in `.env` in the
server's working directory (environment variables take precedence).

| Variable | Default | Description |
|---|---|---|
| `EFG_MCP_READONLY` | `true` | The server is **read-only by default**. Write tools (buy, sell, cancel, amend, fund orders) are registered only when this is explicitly set to `false`; unset, empty, or any other value keeps them off. |
| `EFG_MCP_MAX_ORDER_VALUE_EGP` | `1000` | Maximum single order value (qty × price) in EGP, applied to `buy`, `sell`, `amend_order`, `buy_fund` and `sell_fund`. While the cap is active, market orders (no limit price) are rejected — a limit price is required. Set `0` to disable. |
| `EFG_MCP_MAX_DAILY_ORDERS` | `100` | Maximum orders sent to the API per Cairo calendar day; in-memory, so it also resets on server restart. Set `0` to disable. |

## Available Tools (Read-Only Mode, the default)

By default (`EFG_MCP_READONLY` unset or not `false`), Claude can:

**Market data:**
- `quote` — Current price snapshot (last, bid, ask, min/max, change)
- `stock_info` — Detailed trading info for a stock (same as quote, by name)
- `list_stocks` — Full list of all EGX-listed stocks
- `top_movers` — Full tradeable universe sorted by change % (gainers first), computed live over a few seconds
- `trending_stocks` — Most active stocks right now
- `search_stocks` — Find stocks by partial ticker (e.g. "COM" → "COMI")
- `historical_prices` — OHLCV candle data (Day / Week / Month / Year)

**Real-time streaming snapshots:**
- `streaming_quote` — Live price snapshot via Lightstreamer (more current than `quote`)
- `streaming_orders` — Live order status snapshot (use after placing an order)
- `get_safety_settings` — The server's effective safety settings (read-only flag, order value cap, daily limit, orders sent today)

**Portfolio and account:**
- `account_info` — Account details and profile IDs
- `portfolio` — Cash, margin, and buying power summary
- `positions` — All open stock positions
- `position` — Single position by ticker
- `buying_power` — Available buying power for a specific stock

**Orders:**
- `get_order` — Look up an order by ID

**Funds:**
- `funds` — List all EFG mutual funds
- `fund_performance` — Fund NAV performance chart data

## Additional Tools (Write Mode, `EFG_MCP_READONLY=false`)

- `buy` — Place a buy order (a limit price is required while the order value cap is active)
- `sell` — Place a sell order (a limit price is required while the order value cap is active)
- `cancel_order` — Cancel an open order
- `amend_order` — Modify quantity and/or price of an open order (the new qty × price is checked against the cap)

## Security Notes

- Never commit your credentials to source control.
- The server never logs tokens, credentials, or secrets.
- Safety limits are enforced server-side before orders reach the exchange.
