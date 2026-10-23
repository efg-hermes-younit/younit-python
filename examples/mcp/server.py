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

Safety controls:
- EFG_MCP_READONLY=true disables all write tools (buy, sell, cancel, amend)
- EFG_MCP_MAX_ORDER_VALUE_EGP caps single order value in EGP
- EFG_MCP_MAX_DAILY_ORDERS caps total orders per calendar day (UTC)

This script starts the server via the console entry point's module
(equivalent to running `younit-mcp`), so it works without the package
being installed as an editable/console-script entry point.
"""

import argparse
import os
import subprocess
import sys

os.environ.setdefault("EFG_MCP_READONLY", "true")  # Read-only by default

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
