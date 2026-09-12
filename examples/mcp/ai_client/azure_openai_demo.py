"""AI client demo — Azure OpenAI decides which younit MCP tools to call.

Type a plain-English question about EGX stocks, funds, or your portfolio;
the model behind AZURE_OPENAI_DEPLOYMENT_PLAN autonomously picks which
younit MCP tools to call, the demo executes them via the MCP client SDK,
and the model answers using the results. This is not a scripted demo — ask
anything, the model decides the tool-call plan.

The MCP server is always spawned in EFG_MCP_READONLY mode (see
_mcp_bridge.py) — this demo can never place, amend, or cancel a real order.

Setup:
  uv sync --extra dev --extra ai-demo
  cp examples/mcp/ai_client/.env.example examples/mcp/ai_client/.env
  # fill in AZURE_OPENAI_* and the EFG_* credentials
  python examples/mcp/ai_client/azure_openai_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _mcp_bridge import call_tool, connect_to_server, list_tools, to_openai_tools

load_dotenv(Path(__file__).resolve().parent / ".env")

# Imported after load_dotenv() so AZURE_OPENAI_* is already in the environment.
from openai import AzureOpenAI  # noqa: E402

# Azure identifies models by deployment name, not model name.
DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT_PLAN"]

SYSTEM_PROMPT = (
    "You are a trading assistant for the Egyptian Exchange (EGX), backed by younit "
    "MCP tools. The server is running in read-only mode: you cannot place, amend, "
    "or cancel real orders. Call whatever tools you need, in whatever order makes "
    "sense, before giving your final answer."
)


async def main() -> None:
    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )

    async with connect_to_server() as session:
        mcp_tools = await list_tools(session)
        tools = to_openai_tools(mcp_tools)
        print(f"Connected to younit MCP server. {len(tools)} tool(s) available:")
        print(f"  {', '.join(t.name for t in mcp_tools)}\n")
        print("Ask a question (Ctrl-C to quit).\n")

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

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
                response = client.chat.completions.create(
                    model=DEPLOYMENT, messages=messages, tools=tools
                )
                message = response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))

                if not message.tool_calls:
                    print(f"\nAssistant: {message.content}\n")
                    break

                for tool_call in message.tool_calls:
                    name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    print(f"  -> {name}({arguments})")
                    result_text = await call_tool(session, name, arguments)
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": result_text}
                    )


if __name__ == "__main__":
    asyncio.run(main())
