from __future__ import annotations

import asyncio
import argparse

from mcp.shared.memory import create_connected_server_and_client_session

from .mcp_server import mcp


async def run_demo(source: str = "demo", reasoning_mode: str = "rules") -> None:
    """Demonstrate the MCP initialize/list/call lifecycle in memory."""
    async with create_connected_server_and_client_session(mcp) as session:
        initialized = await session.initialize()
        print(f"Connected to MCP server: {initialized.serverInfo.name}")

        tools = await session.list_tools()
        print("\nAvailable tools:")
        for tool in tools.tools:
            print(f"- {tool.name}: {tool.description}")

        resources = await session.list_resources()
        print("\nAvailable resources:")
        for resource in resources.resources:
            print(f"- {resource.uri}")

        prompts = await session.list_prompts()
        print("\nAvailable prompts:")
        for prompt in prompts.prompts:
            print(f"- {prompt.name}")

        result = await session.call_tool(
            "gmail_process_primary_inbox",
            {"source": source, "reasoning_mode": reasoning_mode},
        )
        print("\nInbox tool result:")
        for content in result.content:
            if hasattr(content, "text"):
                print(content.text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstrate the Personal Assistant MCP client")
    parser.add_argument("--source", choices=["demo", "gmail"], default="demo")
    parser.add_argument(
        "--reasoning", choices=["rules", "ollama", "openai"], default="rules"
    )
    args = parser.parse_args()
    asyncio.run(run_demo(args.source, args.reasoning))


if __name__ == "__main__":
    main()
