"""
Module 14 mini project: Local File Assistant.

The client half. It launches file_server.py as a subprocess, discovers the tools
that server offers over MCP, hands them to an agent, and answers questions about
a folder of notes.

The thing to notice is what is missing. This file contains no file reading code,
no directory listing, no search. It does not import file_server. It learns what
the server can do at runtime, over a protocol, and the tools could just as
easily come from a server written by someone else in another language.

    tools      list what the server offers, no model call
    resources  list MCP resources, which are not tools
    ask        answer a question using the server's tools
    call       run one tool directly, without a model

Usage:
    python file_assistant.py tools
    python file_assistant.py call --tool list_notes
    python file_assistant.py call --tool search_notes --args "{\"query\": \"retention\"}"
    python file_assistant.py ask --question "when does data retention change, and to what"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (
    ConfigError,
    active_model_name,
    arun_with_fallback,
    describe_api_error,
)

HERE = Path(__file__).resolve().parent
SERVER = HERE / "file_server.py"

SYSTEM_PROMPT = (
    "You answer questions about a folder of work notes, using the tools "
    "provided.\n"
    "Start with list_notes or search_notes if you do not know which file holds "
    "the answer. Read a note in full before quoting it.\n"
    "Answer only from the notes. If they do not cover the question, say so.\n"
    "Name the file each fact came from.\n"
    "If two notes disagree, say which is more recent and prefer it."
)

# How the client launches the server. This dictionary is the entire integration:
# a command to run and a transport to speak. Swapping in someone else's MCP
# server means changing these lines and nothing else.
SERVER_CONFIG = {
    "notes": {
        "command": sys.executable,
        "args": [str(SERVER)],
        "transport": "stdio",
    }
}


def make_client() -> MultiServerMCPClient:
    if not SERVER.exists():
        raise ConfigError(f"server not found: {SERVER}")
    return MultiServerMCPClient(SERVER_CONFIG)


def unwrap(result) -> str:
    """
    Flatten an MCP tool result into text.

    Tools return a list of content blocks rather than a string, because MCP
    allows a tool to return text, images or embedded resources. For these tools
    it is always one text block.
    """
    if isinstance(result, list):
        return "\n".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in result
        )
    return str(result)


async def show_tools() -> None:
    tools = await make_client().get_tools()

    print(f"the server offers {len(tools)} tool(s):")
    print()
    for tool in tools:
        print(f"name: {tool.name}")
        for line in (tool.description or "").strip().splitlines():
            print(f"    {line.strip()}")
        for argument, spec in tool.args.items():
            print(f"    arg {argument} ({spec.get('type', '?')})")
        print()

    print("this list was discovered at runtime by asking the server, not")
    print("imported from it. no model was called.")


async def show_resources() -> None:
    """
    Resources are addressed by URI and read by the client, not chosen by a model.

    The server exposes notes://{name} as a template rather than a fixed list, so
    it appears under resource templates.
    """
    client = make_client()
    async with client.session("notes") as session:
        listed = await session.list_resources()
        templates = await session.list_resource_templates()

        print("resources:")
        for resource in listed.resources:
            print(f"  {resource.uri}")
        if not listed.resources:
            print("  none listed directly")

        print()
        print("resource templates:")
        for template in templates.resourceTemplates:
            print(f"  {template.uriTemplate}")

        print()
        print("reading notes://onboarding.md directly:")
        content = await session.read_resource("notes://onboarding.md")
        text = content.contents[0].text if content.contents else ""
        print("  " + "\n  ".join(text.splitlines()[:4]))

    print()
    print("a resource is content the client fetches. a tool is an action the")
    print("model decides to take. no model was called here either.")


async def call_tool(name: str, raw_args: str) -> None:
    """Run one tool directly. Useful for checking the server without a model."""
    tools = {tool.name: tool for tool in await make_client().get_tools()}
    if name not in tools:
        print(f"no such tool: {name}. available: {', '.join(sorted(tools))}")
        return

    arguments = json.loads(raw_args) if raw_args else {}
    result = await tools[name].ainvoke(arguments)
    print(unwrap(result))


async def ask(question: str, quiet: bool) -> None:
    tools = await make_client().get_tools()

    if not quiet:
        print(f"question: {question}")
        print(f"[{len(tools)} tools loaded from the MCP server]")
        print()

    async def run(model):
        agent = create_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
        return await agent.ainvoke({"messages": [HumanMessage(content=question)]})

    # arun_with_fallback awaits the action. The sync version would need
    # asyncio.run here, which fails inside an already running event loop.
    result = await arun_with_fallback(run, temperature=0.0)
    messages = result["messages"]

    if not quiet:
        for message in messages:
            if isinstance(message, AIMessage):
                for call in message.tool_calls or []:
                    print(f"  calling {call['name']}({call['args']})")
            elif isinstance(message, ToolMessage):
                text = str(message.content).replace("\n", " ")
                print(f"  -> {text[:140]}{'...' if len(text) > 140 else ''}")
        print()

    print(str(messages[-1].text).strip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Answer questions about local notes through an MCP server."
    )
    parser.add_argument("command", choices=("tools", "resources", "ask", "call"))
    parser.add_argument("--question", help="what to ask")
    parser.add_argument("--tool", help="tool name, for the call command")
    parser.add_argument("--args", default="", help="JSON arguments, for the call command")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "tools":
            asyncio.run(show_tools())
        elif args.command == "resources":
            asyncio.run(show_resources())
        elif args.command == "call":
            if not args.tool:
                parser.error("call needs --tool")
            asyncio.run(call_tool(args.tool, args.args))
        else:
            if not args.question:
                parser.error("ask needs --question")
            asyncio.run(ask(args.question, args.quiet))
    except ConfigError as error:
        print(error)
        return 1
    except Exception as error:
        if args.debug:
            raise
        print(describe_api_error(error, active_model_name()))
        print()
        print("run again with --debug to see the full traceback")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
