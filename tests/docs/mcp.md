# MCP Server

The `younit-mcp` command starts a Model Context Protocol server that exposes
EFG ONE trading capabilities to Claude and other MCP clients.

## Installation

```bash
pip install younit
younit-mcp --help
```

## Transports

### stdio (Claude Desktop)

```bash
younit-mcp --transport stdio
```

### HTTP/SSE (programmatic clients)

```bash
younit-mcp --transport sse --port 8000
```

## Claude Desktop Configuration

See [examples/mcp/claude_desktop_setup.md](../examples/mcp/claude_desktop_setup.md) for
the full configuration block.

## Safety Controls

All safety controls are configured via environment variables — never in code.

| Variable | Default | Description |
|---|---|---|
| `EFG_MCP_READONLY` | `false` | Disable all write tools (recommended for most users) |
| `EFG_MCP_MAX_ORDER_VALUE_EGP` | `1000` | Max single order value in EGP (0 = disabled) |
| `EFG_MCP_MAX_DAILY_ORDERS` | `100` | Max orders per calendar day UTC (0 = disabled) |

## Available Tools

### Read Tools (always available)

| Tool | Description |
|---|---|
| `quote` | Current price snapshot for a stock |
| `market_status` | Whether the EGX market is currently open or closed, live |
| `account_info` | Account details and profile IDs |
| `portfolio` | Cash and margin portfolio summary |
| `positions` | All open stock positions |
| `position` | Single position by symbol |
| `positions_split` | Positions reliably split into stocks vs funds |
| `buying_power` | Available buying power for a stock |
| `top_movers` | Full tradeable universe sorted by change %, gainers first (live, takes a few seconds) |
| `trending_stocks` | Most active stocks (includes same-day/T0 eligibility classification) |
| `search_stocks` | Search stocks by ticker or name (includes same-day/T0 eligibility classification) |
| `list_by_class` | Stocks filtered by one or more security classifications (e.g. OTC) |
| `list_same_day_eligible` | Stocks eligible for same-day (T0) trading |
| `list_otc` | OTC-classified stocks |
| `get_order` | Fetch an order by ID |
| `funds` | List available investment funds |
| `fund_performance` | Fund performance chart data |
| `fund_positions` | Open fund positions (confirmed empty for this account — see `positions_split`) |
| `stock_info` | Detailed trading info for a stock (same data as `quote`) |
| `list_stocks` | Full list of all EGX-listed stocks (includes same-day/T0 eligibility classification) |
| `historical_prices` | OHLCV candle data (Day / Week / Month / Year) |
| `streaming_quote` | Live price snapshot via the Lightstreamer feed |
| `streaming_orders` | Live order status snapshot via the ActiveOrders stream |

### Write Tools (only when `EFG_MCP_READONLY=false`)

| Tool | Description |
|---|---|
| `buy` | Place a limit or market buy order |
| `sell` | Place a limit or market sell order (t2/t0/t1 settlement via `settlement`) |
| `cancel_order` | Cancel an open order |
| `amend_order` | Modify quantity/price of an open order |
| `buy_fund` | Place a buy order for a mutual fund |
| `sell_fund` | Place a sell (redemption) order for a mutual fund |
| `cancel_fund_order` | Cancel an open fund order |

## Example Prompt

With the MCP server connected to Claude Desktop, you can ask:

> "What's the current price of COMI and how is it performing today?"

> "Show me my portfolio and highlight positions with losses over 5%."

> "Buy 10 shares of HRHO at a limit price 0.5% below the current market price."
  *(requires `EFG_MCP_READONLY=false`)*
