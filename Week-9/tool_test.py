"""
Week 9 Practice: Test Simple Tool Calls

Tests every tool function directly — no agent loop, no API key needed.
Results are displayed as a Rich table so pass/fail is immediately clear.

Run:
    python tool_test.py
"""

import os

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tools import calculate, convert_units, list_notes, save_note

console = Console()


def run_tests() -> list[dict]:
    """
    Run all tool tests and return a list of result dicts for the table.
    Each dict has: tool, description, expected, actual, passed.
    """
    results = []

    # calculate 
    calc_cases = [
        ("2 ** 10",            "power",          "1024"),
        ("sqrt(144)",          "square root",    "12.0"),
        ("(15 / 100) * 2500",  "percentage",     "375.0"),
        ("pi * 5 ** 2",        "circle area r=5","78.539"),
    ]
    for expr, desc, expected_fragment in calc_cases:
        result = calculate(expr)
        passed = expected_fragment in result
        results.append({
            "tool": "calculate",
            "description": desc,
            "actual": result,
            "passed": passed,
        })

    # Security: make sure arbitrary code can't slip through
    bad_result = calculate('__import__("os").system("echo HACKED")')
    results.append({
        "tool": "calculate",
        "description": "blocks __import__",
        "actual": bad_result[:40],
        "passed": "not defined" in bad_result or "Could not evaluate" in bad_result,
    })

    # convert_units 
    unit_cases = [
        (100, "km",        "miles",      "62.137"),
        (25,  "celsius",   "fahrenheit", "77.00"),
        (0,   "celsius",   "kelvin",     "273.15"),
        (70,  "lbs",       "kg",         "31.751"),
        (1,   "m",         "feet",       "3.2808"),
    ]
    for value, f, t, expected_fragment in unit_cases:
        result = convert_units(value, f, t)
        passed = expected_fragment in result
        results.append({
            "tool": "convert_units",
            "description": f"{value} {f} → {t}",
            "actual": result,
            "passed": passed,
        })

    # Unsupported conversion should give a clear message, not crash
    bad_conv = convert_units(5, "bananas", "apples")
    results.append({
        "tool": "convert_units",
        "description": "unsupported → clear message",
        "actual": bad_conv[:40] + "...",
        "passed": "not supported" in bad_conv,
    })

    # save_note / list_notes 
    if os.path.exists("notes.json"):
        os.remove("notes.json")

    empty = list_notes()
    results.append({
        "tool": "list_notes",
        "description": "empty state",
        "actual": empty,
        "passed": "No notes" in empty,
    })

    r1 = save_note("Shopping list", "Rice, dal, vegetables, tea")
    r2 = save_note("Meeting notes", "Discussed RAG pipeline architecture")
    results.append({
        "tool": "save_note",
        "description": "save two notes",
        "actual": r1,
        "passed": "saved successfully" in r1 and "saved successfully" in r2,
    })

    listed = list_notes()
    results.append({
        "tool": "list_notes",
        "description": "list after saving",
        "actual": listed,
        "passed": "Shopping list" in listed and "Meeting notes" in listed,
    })

    if os.path.exists("notes.json"):
        os.remove("notes.json")

    return results


def main():
    console.print()
    console.rule("[bold cyan]Week 9 — Tool Tests[/]")
    console.print()

    results = run_tests()

    #  Results table 
    table = Table(box=box.ROUNDED, show_lines=True, title="Tool Test Results")
    table.add_column("Tool",        style="cyan",  no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Output",      style="dim",   max_width=40)
    table.add_column("Status",      justify="center")

    all_passed = True
    for r in results:
        status = "[bold green]✓ PASS[/]" if r["passed"] else "[bold red]✗ FAIL[/]"
        if not r["passed"]:
            all_passed = False
        table.add_row(r["tool"], r["description"], r["actual"], status)

    console.print(table)
    console.print()

    if all_passed:
        console.print(
            Panel(
                "[bold green]All tests passed.[/]\n"
                "Tools are verified and ready for the agent.",
                border_style="green",
            )
        )
    else:
        failed = [r["description"] for r in results if not r["passed"]]
        console.print(
            Panel(
                f"[bold red]Some tests failed:[/] {', '.join(failed)}",
                border_style="red",
            )
        )
    console.print()


if __name__ == "__main__":
    main()
