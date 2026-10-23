# MCP Server

The `younit-mcp` command exposes the SDK to MCP clients. Start in read-only
mode until configuration has been verified.

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
EFG_MCP_READONLY=true younit-mcp --transport stdio
```

For SSE, use `younit-mcp --transport sse --port 8000`. Configure
`EFG_MCP_READONLY=true` in the environment on Windows as well.

See [Claude Desktop setup](../examples/mcp/claude_desktop_setup.md) for
client configuration and [the tool and safety reference](../tests/docs/mcp.md)
for available tools and safety controls. Non-credential configuration
continues to use its existing `EFG_` environment variables.
