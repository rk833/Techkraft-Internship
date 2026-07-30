"""
Week 9 Deliverable: Basic Agent Demo

A tool-using assistant demonstrating the core difference between a
chatbot and an agent:

  Chatbot : input → LLM → text response (always the same flow)
  Agent   : input → LLM → decides whether/which tool to call
                        → calls tool → observes result
                        → LLM → final response

The model decides:
  - WHETHER a tool is needed at all
  - WHICH of the four tools to use
  - WHAT arguments to pass to it

This is the "planning and action loop" from Week 9's topics.
Gemini's automatic function calling handles the loop — you pass
Python functions as tools, and the SDK handles schema generation,
invocation, and feeding the result back.

Tools: calculate | convert_units | save_note | list_notes

Run:
    python agent.py

Requires: GEMINI_API_KEY in .env
"""

import os

from dotenv import load_dotenv
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from tools import calculate, convert_units, list_notes, save_note

load_dotenv()

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

console = Console()
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """You are a helpful assistant with access to tools
for math calculations, unit conversions, and note-taking.

Use tools when the user's request clearly calls for one:
- Use calculate for any arithmetic or math
- Use convert_units for unit conversions
- Use save_note when the user asks to save or remember something
- Use list_notes when the user asks what notes exist

For general questions outside these tools, reply directly without
calling any tool.
"""


def print_banner():
    """Print the startup banner with available tools and example prompts."""
    console.print()
    console.print(Rule("[bold cyan]Week 9 — Basic Agent Demo[/]"))
    console.print()

    # Tools table
    tools_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    tools_table.add_column("Tool", style="yellow")
    tools_table.add_column("Does", style="dim")
    tools_table.add_row("calculate",    "math expressions, percentages, sqrt, pi...")
    tools_table.add_row("convert_units","lengths, weights, temperatures")
    tools_table.add_row("save_note",    "save a note to notes.json")
    tools_table.add_row("list_notes",   "see what notes have been saved")

    console.print(Panel(tools_table, title="[bold]Available Tools[/]", border_style="cyan"))
    console.print()

    # Example prompts
    examples = [
        "what is 2 to the power of 16?",
        "convert 30 celsius to fahrenheit",
        "save a note called plans: finish week 9",
        "what notes have I saved?",
        "what is 15% of 8500?",
        "what is the capital of Nepal?",
    ]
    example_text = "\n".join(f"  [dim]•[/] [italic]{e}[/]" for e in examples)
    console.print(
        Panel(
            example_text,
            title="[bold]Try these prompts[/]",
            border_style="dim",
            subtitle="[dim]last one needs no tool — agent answers directly[/]",
        )
    )
    console.print()
    console.print("[dim]Type [bold]quit[/bold] to exit.[/]")
    console.print()


def print_tool_call(tool_name: str, args: dict):
    """Print a subtle inline line showing which tool was invoked."""
    args_str = ", ".join(f"{k}=[yellow]{v!r}[/]" for k, v in args.items())
    console.print(f"  [dim]→ tool:[/] [bold yellow]{tool_name}[/]  [dim]{args_str}[/]")


def print_agent_response(text: str):
    console.print(
        Panel(text, title="[bold cyan]Agent[/]", border_style="cyan", padding=(0, 1))
    )
    console.print()


def print_error(message: str):
    console.print(
        Panel(f"[red]{message}[/]", title="[bold red]Error[/]", border_style="red")
    )
    console.print()


def run_agent():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        console.print(
            Panel(
                "No [bold]GEMINI_API_KEY[/] found in [yellow].env[/].\n"
                "Copy [yellow].env.example[/] to [yellow].env[/] and add your key.\n"
                "Get a free key at [link]https://aistudio.google.com[/link]",
                title="[bold red]Setup Required[/]",
                border_style="red",
            )
        )
        return

    client = genai.Client(api_key=api_key)
    history = []

    print_banner()

    while True:
        try:
            user_input = console.input("[bold green]You:[/] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            console.print("[dim]Goodbye.[/]")
            break

        history.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_input)],
            )
        )

        console.print()

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[calculate, convert_units, save_note, list_notes],
                    temperature=0.2,
                ),
            )
        except Exception as error:
            print_error(str(error))
            history.pop()
            continue

        # Show which tools were called, if any
        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                print_tool_call(fc.name, dict(fc.args))

        history.append(response.candidates[0].content)
        print_agent_response(response.text)


if __name__ == "__main__":
    run_agent()
