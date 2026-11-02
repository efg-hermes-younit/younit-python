# MCP Server

The `younit-mcp` command exposes the SDK to MCP clients. The server is
**read-only by default**: write tools are registered only when
`EFG_MCP_READONLY=false` is set explicitly (unset, empty, or any other value
keeps it read-only). The `EFG_MCP_*` safety settings can be set in the
environment or in `.env` in the server's working directory, like `TRADING_ID`
and `API_KEY`; environment variables take precedence. Invalid values fall back
to the safe defaults (read-only, 1000 EGP, 100 orders per day). Leave it
read-only until configuration has been verified.

## Authentication

Set the following in the MCP server environment or in `.env` in its working
directory. Never commit `.env` or real credential values.

```dotenv
TRADING_ID=your-trading-id
API_KEY=your-api-key
```

The server and `examples/mcp/server.py` use `Client()` and therefore share
the SDK authentication flow:

- `POST https://tradingapis.efghermesone.com/api/public-keys/token`
- JSON body: `{"tradingId": "<TRADING_ID>", "secret": "<API_KEY>"}`
- REST requests use the returned Bearer token.
- Lightstreamer uses `TRADING_ID` as the username and the token as its password.
- Tokens refresh five minutes before expiry. An API 401 causes one
  re-authentication and retry, including updating the streaming password.
- Missing credentials are reported by name; token errors include the HTTP
  status and a credential-redacted server message.

The production response contains `accessToken`, `expiresIn`, and `tokenType`
inside `data`; the parser also accepts those fields at the top level. Parsing
is isolated in `_parse_token_response`; HTML and invalid JSON responses fail
explicitly, with no alternative auth flow.
REST endpoint hosts and streaming hosts are unchanged.

## Running

```bash
younit-mcp --transport stdio        # read-only (default)
EFG_MCP_READONLY=false younit-mcp   # enables write tools, subject to the safety caps
```

For SSE, use `younit-mcp --transport sse --port 8000`. Write tools exist only
when `EFG_MCP_READONLY=false`; `EFG_MCP_MAX_ORDER_VALUE_EGP` (default 1000)
applies to `buy`, `sell`, `amend_order`, `buy_fund` and `sell_fund`, and while
it is active market orders (no limit price) are rejected.

Daily order limit (EFG_MCP_MAX_DAILY_ORDERS, default 100): the number of orders the MCP server will send to the API per day. Orders blocked by the other safety checks don't count. The count is kept in the server's memory, so it resets at midnight Cairo time and whenever the server restarts. It's meant to stop a runaway AI agent within a session. It isn't an account-wide limit, and it doesn't count orders placed in the Younit app or through the SDK directly.

The two limits accept whole numbers written as `250`, ` 250 ` or `250.0`. A fractional value is rounded down (`250.9` becomes 250), and a positive value that would round down to 0 (`0.5`) falls back to the default instead of turning the limit off. Anything else, including negative numbers, also falls back to the default. `0` turns a limit off.

The read-only `get_safety_settings` tool is always available, also in read-only mode. It returns the effective values (`read_only`, `max_order_value_egp`, `max_daily_orders` and `orders_sent_today`) and never any credentials.

See [Claude Desktop setup](../examples/mcp/claude_desktop_setup.md) for
client configuration and [the tool and safety reference](../tests/docs/mcp.md)
for available tools and safety controls. Non-credential configuration
continues to use its existing `EFG_` environment variables.
