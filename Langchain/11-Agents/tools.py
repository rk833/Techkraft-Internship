"""
The three tools the agent can call.

Kept in their own file because a tool is ordinary Python. The interesting part
of an agent is not the tools, it is that the model decides which one to call
and with what arguments.

Two things matter when writing a tool:

    the docstring is the model's only manual for it
    the argument schema is what the model has to fill in

Both are sent to the model with every request, so they are prompt engineering
rather than documentation.
"""

import ast
import operator
from urllib.parse import quote

import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field

REQUEST_TIMEOUT = 20

# Wikipedia returns 403 to any request without a User-Agent identifying the
# caller. The long unmaintained "wikipedia" PyPI package does not send one, so
# it fails on every call now. Talking to the API directly is both fewer
# dependencies and less to go wrong.
WIKIPEDIA_HEADERS = {"User-Agent": "LangChainLearning/1.0 (educational project)"}

# Only these operations are allowed in the calculator. Anything else is
# rejected before it runs.
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# https://open-meteo.com/en/docs, WMO weather interpretation codes
WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class CalculatorInput(BaseModel):
    """Explicit schema, so the model is told exactly what to send."""

    expression: str = Field(
        description="An arithmetic expression, for example '18 * 4.5' or '(120 - 15) / 7'"
    )


def _evaluate(node):
    """
    Walk a parsed expression, allowing only arithmetic.

    eval() would be one line and is the wrong answer. A tool argument comes
    from a language model, which may be repeating something a user wrote, so
    it is untrusted input. eval("__import__('os').system('...')") runs.
    Parsing to a syntax tree and refusing anything that is not a number or an
    allowed operator makes that impossible rather than unlikely.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("only numbers are allowed")

    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        return OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
        return OPERATORS[type(node.op)](_evaluate(node.operand))

    raise ValueError(f"unsupported expression element: {type(node).__name__}")


@tool("calculator", args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression. Use this for any sum, however simple.

    Handles + - * / // % and ** with brackets. Does not handle words, units,
    currency symbols or variables, so pass digits and operators only.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _evaluate(tree.body)
    except ZeroDivisionError:
        return "error: division by zero"
    except (SyntaxError, ValueError) as error:
        return f"error: {error}"

    # trim a pointless trailing .0 so the model sees 81 rather than 81.0
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)


@tool("wikipedia")
def wikipedia_lookup(query: str) -> str:
    """Look up factual background on a topic, person, place or event on Wikipedia.

    Use for things that are broadly known and stable. Do not use for current
    weather, live prices, or anything happening right now.
    """
    # Two steps: search for the best matching title, then fetch its summary.
    # Searching first means a rough query still lands on the right page.
    try:
        found = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "format": "json",
            },
            headers=WIKIPEDIA_HEADERS,
            timeout=REQUEST_TIMEOUT,
        ).json()
    except requests.RequestException as error:
        return f"could not reach Wikipedia: {error}"

    hits = found.get("query", {}).get("search", [])
    if not hits:
        return f"no Wikipedia page found for '{query}'"

    title = hits[0]["title"]
    try:
        summary = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title, safe='')}",
            headers=WIKIPEDIA_HEADERS,
            timeout=REQUEST_TIMEOUT,
        ).json()
    except requests.RequestException as error:
        return f"could not reach Wikipedia: {error}"

    extract = summary.get("extract")
    if not extract:
        return f"no summary available for '{title}'"

    return f"{title}: {extract}"


@tool("weather")
def weather(city: str) -> str:
    """Get the current weather for a named city or town.

    Returns temperature in Celsius, humidity, wind speed and conditions right
    now. Only current conditions, not a forecast. Pass a plain place name such
    as 'Kathmandu' or 'Porto'.
    """
    try:
        found = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=REQUEST_TIMEOUT,
        ).json()
    except requests.RequestException as error:
        return f"could not reach the geocoding service: {error}"

    results = found.get("results")
    if not results:
        return f"no place called '{city}' was found"

    place = results[0]
    try:
        data = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            },
            timeout=REQUEST_TIMEOUT,
        ).json()
    except requests.RequestException as error:
        return f"could not reach the weather service: {error}"

    current = data["current"]
    conditions = WEATHER_CODES.get(current["weather_code"], "unknown conditions")

    return (
        f"{place['name']}, {place.get('country', '')}: {conditions}, "
        f"{current['temperature_2m']} C, "
        f"humidity {current['relative_humidity_2m']}%, "
        f"wind {current['wind_speed_10m']} km/h"
    )


ALL_TOOLS = [calculator, wikipedia_lookup, weather]
