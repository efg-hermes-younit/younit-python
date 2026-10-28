"""MCPB entry point: runs the younit-mcp server over stdio."""

import sys

from younit.mcp_server.server import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--transport", "stdio"]
    main()
