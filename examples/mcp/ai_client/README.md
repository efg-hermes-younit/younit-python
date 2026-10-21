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

Every demo connects through `_mcp_bridge.connect_to_server()`, which
**always** spawns the MCP server with `EFG_MCP_READONLY=true` — hardcoded,
not something a demo script can override. The LLM can look up quotes,
positions, funds, and orders, but it can never place, amend, or cancel a
real order through these demos, no matter what you ask it to do.

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
