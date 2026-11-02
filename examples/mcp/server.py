"""Example — Run the younit MCP server (stdio or SSE transport).

Usage:
  python examples/mcp/server.py                          # stdio, for Claude Desktop
  python examples/mcp/server.py --transport sse           # SSE, port 8000
  python examples/mcp/server.py --transport sse --port 9000

Claude Desktop config (~/.config/claude/claude_desktop_config.json):

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

See examples/mcp/claude_desktop_setup.md for the full configuration guide.

Safety settings. Put them in the environment (including the "env" block above)
or in a .env file in the working directory; environment variables take
precedence. Invalid values fall back to the defaults.
- EFG_MCP_READONLY (default: true). The server is read-only; write tools
  (buy, sell, cancel, amend) exist only when this is exactly "false".
- EFG_MCP_MAX_ORDER_VALUE_EGP (default: 1000). Caps a single order's value
  (qty x price) in EGP; 0 disables. While active, market orders (no limit
  price) are rejected.
- EFG_MCP_MAX_DAILY_ORDERS (default: 100). Caps orders sent to the API per
  Cairo calendar day; in memory, so it also resets on restart; 0 disables.

This script starts the server via the console entry point's module
(equivalent to running `younit-mcp`), so it works without the package
being installed as an editable/console-script entry point.
"""

import argparse
import subprocess
import sys

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument(
    "--transport",
    choices=["stdio", "sse"],
    default="stdio",
    help="Transport protocol (default: stdio)",
)
parser.add_argument(
    "--port",
    type=int,
    default=8000,
    help="Port for SSE transport (default: 8000, ignored for stdio)",
)
args = parser.parse_args()

cmd = [sys.executable, "-m", "younit.mcp_server.server", "--transport", args.transport]
if args.transport == "sse":
    cmd += ["--port", str(args.port)]
    print(f"Starting MCP server (SSE) on http://localhost:{args.port}/sse", file=sys.stderr)

subprocess.run(cmd, check=True)  # noqa: S603 — fixed argv: sys.executable + this package's own module
