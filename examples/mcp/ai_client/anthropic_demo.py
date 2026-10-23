"""AI client demo — Claude decides which younit MCP tools to call.

Type a plain-English question about EGX stocks, funds, or your portfolio;
the model (ANTHROPIC_MODEL, default claude-sonnet-4-6) autonomously picks
which younit MCP tools to call, the demo executes them via the MCP client
SDK, and the model answers using the results. This is not a scripted demo —
ask anything, the model decides the tool-call plan.

The MCP server is always spawned in EFG_MCP_READONLY mode (see
_mcp_bridge.py) — this demo can never place, amend, or cancel a real order.

Setup:
  uv sync --extra dev --extra ai-demo
  cp examples/mcp/ai_client/.env.example examples/mcp/ai_client/.env
  # fill in ANTHROPIC_API_KEY plus TRADING_ID and API_KEY
  python examples/mcp/ai_client/anthropic_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mcp_bridge import call_tool, connect_to_server, list_tools, to_anthropic_tools

load_dotenv(Path(__file__).resolve().parent / ".env")

# Imported after load_dotenv() so ANTHROPIC_API_KEY is already in the environment.
from anthropic import Anthropic  # noqa: E402

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 2048

SYSTEM_PROMPT = (
    "You are a trading assistant for the Egyptian Exchange (EGX), backed by younit "
    "MCP tools. The server is running in read-only mode: you cannot place, amend, "
    "or cancel real orders. Call whatever tools you need, in whatever order makes "
    "sense, before giving your final answer."
)


async def main() -> None:
    client = Anthropic()

    async with connect_to_server() as session:
        mcp_tools = await list_tools(session)
        tools = to_anthropic_tools(mcp_tools)
        print(f"Connected to younit MCP server. {len(tools)} tool(s) available:")
        print(f"  {', '.join(t.name for t in mcp_tools)}\n")
        print("Ask a question (Ctrl-C to quit).\n")

        messages: list[dict] = []

        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                return
            if not question:
                continue
            if question.lower() in {"exit", "quit"}:
                print("Bye.")
                return

            messages.append({"role": "user", "content": question})

            while True:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=tools,
                )
                messages.append({"role": "assistant", "content": response.content})

                tool_uses = [block for block in response.content if block.type == "tool_use"]
                if not tool_uses:
                    text = "".join(block.text for block in response.content if block.type == "text")
                    print(f"\nAssistant: {text}\n")
                    break

                tool_results = []
                for block in tool_uses:
                    print(f"  -> {block.name}({block.input})")
                    result_text = await call_tool(session, block.name, block.input)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
                    )
                messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    asyncio.run(main())
