"""
Module 11 mini project: AI Utility Agent.

An agent with three tools, choosing for itself which to call and with what
arguments.

    calculator  arithmetic, evaluated safely
    wikipedia   factual background
    weather     current conditions for a city

Everything before this module ran a fixed pipeline: the code decided what
happened and in what order. Here the model decides. It can call no tools, one
tool, several tools in sequence, or the same tool twice with different
arguments, and none of that is written down anywhere.

    ask     answer a question, printing each tool call as it happens
    tools   list the tools exactly as the model sees them, no API call

Usage:
    python utility_agent.py tools
    python utility_agent.py ask --question "what is 18 * 4.5"
    python utility_agent.py ask --question "what is the weather in Kathmandu"
    python utility_agent.py ask --question "who was Ada Lovelace and what is 2 to the power of 10"
    python utility_agent.py ask --question "..." --quiet
"""

import argparse
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, describe_api_error, run_with_fallback
from tools import ALL_TOOLS

# The system prompt shapes when the agent reaches for a tool at all. Without
# the arithmetic line it answers simple sums from memory, which is usually
# right and occasionally, silently, wrong.
SYSTEM_PROMPT = (
    "You are a helpful assistant with tools.\n"
    "Use the calculator for every arithmetic question, even easy ones. Never "
    "do arithmetic yourself.\n"
    "Use wikipedia for factual background about people, places, things and "
    "events.\n"
    "Use weather for current conditions in a named place.\n"
    "If a question needs several tools, call them one at a time.\n"
    "If no tool fits, just answer directly.\n"
    "Answer in plain prose, briefly."
)


def show_tools() -> None:
    """
    Print each tool exactly as the model receives it.

    This is the whole interface the model has. It never sees the code, only the
    name, the description and the argument schema, which is why those three
    things decide whether an agent works.
    """
    for tool in ALL_TOOLS:
        print(f"name: {tool.name}")
        print("description:")
        for line in tool.description.strip().splitlines():
            print(f"    {line.strip()}")
        print("arguments:")
        for argument, spec in tool.args.items():
            print(f"    {argument} ({spec.get('type', '?')}): {spec.get('description', '')}")
        print()

    print("no API call was made. this is the model's entire manual for the tools.")


def describe_step(message, quiet: bool) -> None:
    """Print tool calls and results as the agent works through them."""
    if quiet:
        return

    if isinstance(message, AIMessage):
        for call in message.tool_calls or []:
            print(f"  calling {call['name']}({call['args']})")
    elif isinstance(message, ToolMessage):
        text = str(message.content).replace("\n", " ")
        print(f"  -> {text[:160]}{'...' if len(text) > 160 else ''}")


def ask(question: str, quiet: bool) -> None:
    def run(model):
        # create_agent builds a LangGraph loop: call the model, run any tools
        # it asked for, feed the results back, repeat until it stops asking.
        agent = create_agent(model=model, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)
        return agent.invoke({"messages": [HumanMessage(content=question)]})

    if not quiet:
        print(f"question: {question}")
        print()

    result = run_with_fallback(run, temperature=0.0)
    messages = result["messages"]

    for message in messages:
        describe_step(message, quiet)

    final = messages[-1]
    tool_calls = sum(len(m.tool_calls or []) for m in messages if isinstance(m, AIMessage))

    if not quiet:
        print()
    print(str(final.text).strip())

    if not quiet:
        print()
        print(f"[{tool_calls} tool call(s), {len(messages)} messages in the loop]")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="An agent that chooses between a calculator, Wikipedia and weather."
    )
    parser.add_argument("command", choices=("ask", "tools"))
    parser.add_argument("--question", help="what to ask")
    parser.add_argument(
        "--quiet", action="store_true", help="print only the final answer"
    )
    parser.add_argument("--debug", action="store_true", help="show the full traceback")
    args = parser.parse_args()

    try:
        if args.command == "tools":
            show_tools()
        else:
            if not args.question:
                parser.error("ask needs --question")
            ask(args.question, args.quiet)
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
