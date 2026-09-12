# younit

Python SDK and MCP server for the EFG ONE Trading API.

[![PyPI](https://img.shields.io/pypi/v/younit-sdk)](https://pypi.org/project/younit-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/younit-sdk)](https://pypi.org/project/younit-sdk/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![CI](https://github.com/efg-hermes-younit/younit-python/actions/workflows/ci.yml/badge.svg)](https://github.com/efg-hermes-younit/younit-python/actions/workflows/ci.yml)
## Installation

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

Copy `.env.example` to `.env` in the project root and fill in your credentials (`.env` is already gitignored — never commit it):

```bash
cp .env.example .env
```

```dotenv
EFG_PARTNER_ID=your-partner-id
EFG_PARTNER_SECRET=your-partner-secret
EFG_TRADING_UUID=your-trading-uuid
```

Full configuration reference: [docs/reference.md](docs/reference.md).

## Usage

See [`examples/`](examples/) for complete, runnable examples covering quotes, portfolio, orders, funds, streaming, and the MCP server — start with [`examples/01_quote.py`](examples/01_quote.py).

**Method naming convention**: unprefixed methods (`buy()`, `sell()`, `positions()`, etc.) operate on stocks. Fund-equivalent methods use an explicit `_fund` suffix (`buy_fund()`, `sell_fund()`, `fund_positions()`, etc.).

## MCP Server

```bash
younit-mcp --transport stdio
```

See [`examples/mcp/claude_desktop_setup.md`](examples/mcp/claude_desktop_setup.md) for Claude Desktop configuration.

The [`examples/mcp/ai_client/`](examples/mcp/ai_client/) demos show an LLM (OpenAI, Azure OpenAI, or Anthropic) autonomously driving these tools — see the extras table above for the install command.

## Development

```bash
uv sync --extra dev
uv run pytest tests/unit/
uv run ruff check src tests
uv run mypy src
```

`tests/live/` contains real-money live-trading tests, gated separately — see [tests/live/README.md](tests/live/README.md). Not part of the standard workflow above.

## Security

See [SECURITY.md](SECURITY.md) before reporting vulnerabilities.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).