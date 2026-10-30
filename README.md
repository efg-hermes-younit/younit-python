# younit

Official Python SDK and MCP server for the Younit API.

[![PyPI](https://img.shields.io/pypi/v/younit-sdk)](https://pypi.org/project/younit-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/younit-sdk)](https://pypi.org/project/younit-sdk/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](https://github.com/efg-hermes-younit/younit-python/blob/master/LICENSE)
[![CI](https://github.com/efg-hermes-younit/younit-python/actions/workflows/ci.yml/badge.svg)](https://github.com/efg-hermes-younit/younit-python/actions/workflows/ci.yml)

## Installation

**From PyPI (coming soon).** Requires Python 3.11 or newer. Until then, install from source (below).

```bash
pip install younit-sdk
# or, with uv
uv add younit-sdk
```

This installs the `younit` Python package and the `younit-mcp` command.

### From source (examples and development)

Requires [uv](https://github.com/astral-sh/uv) — it manages Python versions itself, so you don't need Python pre-installed.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then clone and install:

```bash
git clone https://github.com/efg-hermes-younit/younit-python.git
cd younit-python
uv sync
```

| You want to... | Command |
|---|---|
| Use the SDK, run examples, run the MCP server | `uv sync` |
| Run tests, lint, type-check | `uv sync --extra dev` |
| Run the `examples/mcp/ai_client/` AI-driven demos | `uv sync --extra dev --extra ai-demo` |

> `uv sync --extra X` replaces your environment with exactly what's named — it does not add to what's already installed. Always combine extras you want in one command (as above), or you'll silently lose previously-installed ones.

## Credentials

Set your credentials as environment variables, or put them in a `.env` file in your working directory (never commit it). If you cloned the repository, copy the template first:

```bash
cp .env.example .env
```

```dotenv
TRADING_ID=your-trading-id
API_KEY=your-api-key
```

Alternatively, pass `Client(trading_id="...", api_key="...")`; constructor
arguments override environment variables and `.env`.

Authentication sends JSON `{"tradingId": "<TRADING_ID>", "secret": "<API_KEY>"}`
to `POST https://tradingapis.efghermesone.com/api/public-keys/token`.
REST endpoints remain on that same host. The returned token is used as a
Bearer token for REST and the Lightstreamer password; `TRADING_ID` is the
streaming username. Tokens refresh five minutes before expiry, and an API
401 triggers one re-authentication and retry.

The token response uses `accessToken`, `expiresIn`, and `tokenType`, nested
under `data` in the production response. The parser also accepts these fields
at the top level. Unexpected responses raise an authentication error rather
than falling back to a different authentication method.

Other settings retain their `EFG_` prefix (for example, `EFG_SIMULATION=true`).
Missing credentials are reported by name; credential values are never included
in authentication errors. See [MCP authentication](https://github.com/efg-hermes-younit/younit-python/blob/master/docs/mcp.md#authentication)
for server configuration.

## Usage

See [`examples/`](https://github.com/efg-hermes-younit/younit-python/tree/master/examples) for complete, runnable examples covering quotes, portfolio, orders, funds, streaming, and the MCP server — start with [`examples/01_quote.py`](https://github.com/efg-hermes-younit/younit-python/blob/master/examples/01_quote.py).

**Method naming convention**: unprefixed methods (`buy()`, `sell()`, `positions()`, etc.) operate on stocks. Fund-equivalent methods use an explicit `_fund` suffix (`buy_fund()`, `sell_fund()`, `fund_positions()`, etc.).

## MCP Server

```bash
younit-mcp --transport stdio
```

See [`examples/mcp/claude_desktop_setup.md`](https://github.com/efg-hermes-younit/younit-python/blob/master/examples/mcp/claude_desktop_setup.md) for Claude Desktop configuration.

The [`examples/mcp/ai_client/`](https://github.com/efg-hermes-younit/younit-python/tree/master/examples/mcp/ai_client) demos show an LLM (OpenAI, Azure OpenAI, or Anthropic) autonomously driving these tools — see the extras table above for the install command.

## Development

```bash
uv sync --extra dev
uv run pytest tests/unit/
uv run ruff check src tests
uv run mypy src
```

`tests/live/` contains real-money live-trading tests, gated separately — see [tests/live/README.md](https://github.com/efg-hermes-younit/younit-python/blob/master/tests/live/README.md). Not part of the standard workflow above.

## Security

See [SECURITY.md](https://github.com/efg-hermes-younit/younit-python/blob/master/SECURITY.md) before reporting vulnerabilities.

## License

Apache 2.0 — see [LICENSE](https://github.com/efg-hermes-younit/younit-python/blob/master/LICENSE).

## Contributing

See [CONTRIBUTING.md](https://github.com/efg-hermes-younit/younit-python/blob/master/CONTRIBUTING.md).