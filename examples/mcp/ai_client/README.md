# AI client demos

Three small interactive scripts where a real LLM decides, on its own, which
younit MCP tools to call in response to whatever you type — there's no
scripted question, you drive the conversation.

| Script | Provider |
|---|---|
| `openai_demo.py` | OpenAI |
| `azure_openai_demo.py` | Azure OpenAI |
| `anthropic_demo.py` | Anthropic |

All three share `_mcp_bridge.py`, which spawns `examples/mcp/server.py`
over stdio and converts its tools into each provider's function-calling
format.

## Safety

The demos are **read-only by default**: the AI can look up quotes, positions,
funds and orders, but cannot place, amend or cancel anything.

To allow trading, open `_mcp_bridge.py` and set `READ_ONLY = False` (the
constant right after the imports). A warning is then printed every time a demo
starts, because the AI can then place, amend and cancel **real orders** on your
account. The limits in `.env` still apply: `EFG_MCP_MAX_ORDER_VALUE_EGP` and
`EFG_MCP_MAX_DAILY_ORDERS`.

`EFG_MCP_READONLY` in `.env` or in your environment is **ignored** by the
demos; only `READ_ONLY` in `_mcp_bridge.py` decides.

### Simulation mode is disabled

`EFG_SIMULATION` is temporarily disabled in this version while simulation mode
is being verified. If it is set to anything other than empty, `false`, `0` or
`no` (in `.env` or the environment), the demos print an error and exit with
code 1 before starting the server. Remove `EFG_SIMULATION` to continue.

### What the server receives

The server does not inherit your whole environment (which would include the
LLM provider keys). `_mcp_bridge.py` passes it, explicitly and only when set
and non-empty, `TRADING_ID`, `API_KEY`, `EFG_LOG_LEVEL`, `EFG_SIMULATION`,
`EFG_MCP_MAX_ORDER_VALUE_EGP` and `EFG_MCP_MAX_DAILY_ORDERS` (plus proxy and
CA-bundle variables such as `HTTPS_PROXY` and `SSL_CERT_FILE`), and always an
explicit `EFG_MCP_READONLY` taken from `READ_ONLY`. Values are
never printed. Put them in `examples/mcp/ai_client/.env` (loaded by every demo)
or export them in your shell; the shell wins over `.env`. The server also runs
with `examples/mcp/ai_client/` as its working directory, so any `.env` it reads
itself is that same file, wherever you launched the demo from.

### Safety settings

| Variable | Default | Meaning |
|---|---|---|
| `EFG_MCP_READONLY` | `true` | Ignored by these demos (see `READ_ONLY` above). In `server.py` and `younit-mcp`, write tools exist only when it is exactly `false`. |
| `EFG_MCP_MAX_ORDER_VALUE_EGP` | `1000` | Max value (qty × price) of one order, in EGP; `0` disables. While active, market orders (no limit price) are rejected. Only matters when trading is allowed. |
| `EFG_MCP_MAX_DAILY_ORDERS` | `100` | Max orders sent to the API per day (Cairo time), in memory, so it also resets on server restart; `0` disables. Only matters when trading is allowed. |

Invalid values fall back to these defaults.

## Setup

```bash
uv sync --extra dev --extra ai-demo

cp examples/mcp/ai_client/.env.example examples/mcp/ai_client/.env
# fill in the API key(s) for the provider(s) you want to try, plus
# TRADING_ID / API_KEY — the spawned
# MCP server needs these to authenticate against younit.

python examples/mcp/ai_client/openai_demo.py
```

`uv sync --extra X` syncs your environment to exactly the extras named in that
command — it doesn't add to whatever's already installed, it replaces it. If
you run `uv sync --extra ai-demo` on its own after previously installing the
`dev` extra (pytest, ruff, mypy, etc.), `uv` will silently uninstall all of
that dev tooling because it wasn't named in the command. Always list every
extra you want installed together in one `uv sync` call, as above.

Type `exit` or press Ctrl-C to quit.
