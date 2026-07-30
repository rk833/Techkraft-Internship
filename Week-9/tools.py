"""
Week 9: Tool Implementations

Plain Python functions that the agent can call. Each function has:
  - A clear, specific docstring (Gemini reads this to decide WHEN to
    call the tool and WHAT arguments to pass — the docstring IS the
    tool description, not just documentation)
  - A single responsibility
  - No dangerous side effects

These are tested in isolation by tool_test.py before the agent uses
them — if something breaks in the agent loop, you can immediately rule
out "is the tool broken?" and focus on "did the model call it wrong?"

Tools:
  calculate(expression)              - evaluate a math expression safely
  convert_units(value, from, to)     - unit conversion
  save_note(title, content)          - save a note to notes.json
  list_notes()                       - list all saved note titles
"""

import json
import math
import os
from datetime import datetime

NOTES_FILE = "notes.json"


def calculate(expression: str) -> str:
    """Evaluates a mathematical expression and returns the result.

    Use this for any arithmetic, percentages, or math calculations.
    Supports: +, -, *, /, **, sqrt(), sin(), cos(), pi, and basic math.

    Args:
        expression: The math expression to evaluate, e.g. '2 ** 10'
                    or 'sqrt(144)' or '(15 / 100) * 2500'
    """
    allowed = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "pi": math.pi,
        "e": math.e,
        "abs": abs,
        "round": round,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)  # noqa: S307
        return f"{expression} = {result}"
    except Exception as error:
        return f"Could not evaluate '{expression}': {error}"


CONVERSIONS = {
    # length
    "km_to_m": 1000,
    "m_to_km": 0.001,
    "miles_to_km": 1.60934,
    "km_to_miles": 0.621371,
    "cm_to_m": 0.01,
    "m_to_cm": 100,
    "feet_to_m": 0.3048,
    "m_to_feet": 3.28084,
    # weight
    "kg_to_lbs": 2.20462,
    "lbs_to_kg": 0.453592,
    "g_to_kg": 0.001,
    "kg_to_g": 1000,
}


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Converts a value from one unit to another.

    Supports: km, m, cm, miles, feet (length); kg, g, lbs (weight);
    celsius, fahrenheit, kelvin (temperature).

    Args:
        value: The numeric value to convert.
        from_unit: The unit to convert from, e.g. 'km', 'celsius', 'lbs'.
        to_unit: The unit to convert to, e.g. 'miles', 'fahrenheit', 'kg'.
    """
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    if from_unit == "celsius" and to_unit == "fahrenheit":
        return f"{value}°C = {(value * 9/5) + 32:.2f}°F"
    if from_unit == "fahrenheit" and to_unit == "celsius":
        return f"{value}°F = {(value - 32) * 5/9:.2f}°C"
    if from_unit == "celsius" and to_unit == "kelvin":
        return f"{value}°C = {value + 273.15:.2f}K"
    if from_unit == "kelvin" and to_unit == "celsius":
        return f"{value}K = {value - 273.15:.2f}°C"

    key = f"{from_unit}_to_{to_unit}"
    if key in CONVERSIONS:
        result = value * CONVERSIONS[key]
        return f"{value} {from_unit} = {result:.4f} {to_unit}"

    supported = ", ".join(sorted(set(k.split("_to_")[0] for k in CONVERSIONS)))
    return (
        f"Conversion from '{from_unit}' to '{to_unit}' is not supported. "
        f"Supported units: {supported}, celsius, fahrenheit, kelvin."
    )


def save_note(title: str, content: str) -> str:
    """Saves a note with a title and content to local storage.

    Use this when the user asks to remember, save, note down, or
    write something for later.

    Args:
        title: A short title for the note.
        content: The full content of the note to save.
    """
    notes = _load_notes()
    notes[title] = {
        "content": content,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_notes(notes)
    return f"Note '{title}' saved successfully."


def list_notes() -> str:
    """Lists all saved note titles.

    Use this when the user asks what notes have been saved, or wants
    to see a list of their notes.
    """
    notes = _load_notes()
    if not notes:
        return "No notes saved yet."
    return f"Saved notes ({len(notes)}): {', '.join(notes.keys())}"


def _load_notes() -> dict:
    if os.path.exists(NOTES_FILE):
        with open(NOTES_FILE) as f:
            return json.load(f)
    return {}


def _save_notes(notes: dict) -> None:
    with open(NOTES_FILE, "w") as f:
        json.dump(notes, f, indent=2)
