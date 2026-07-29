"""
Module 01 mini project: AI Joke Generator.

Generates a joke about a topic given by the user, and demonstrates the four
chat model behaviours covered in this module:

    basic       a single call and its response
    temperature the same prompt at different temperature values
    stream      tokens printed as they arrive instead of all at once
    structured  the response parsed into a typed object rather than text

Usage:
    python joke_generator.py "space travel"
    python joke_generator.py "space travel" --mode temperature
    python joke_generator.py "space travel" --mode stream
    python joke_generator.py "space travel" --mode structured
"""

import argparse
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (
    ConfigError,
    active_model_name,
    describe_api_error,
    run_with_fallback,
    stream_with_fallback,
)

# the free tier limits requests per minute, and the temperature mode makes
# several calls in a row, so it pauses between them
SECONDS_BETWEEN_CALLS = 4


class Joke(BaseModel):
    """A joke split into its parts."""

    setup: str = Field(description="the opening line of the joke")
    punchline: str = Field(description="the line that delivers the humour")
    rating: int = Field(description="how funny the joke is, from 1 to 10")


def prompt_for(topic: str) -> str:
    return f"Tell me a short, clean joke about {topic}."


def run_basic(topic: str) -> None:
    """
    One call, one response.

    invoke() returns an AIMessage, not a string. Use .text for the reply:
    .content is a list of content blocks on current models, so printing it
    directly shows internal structure rather than the joke.
    """
    response = run_with_fallback(lambda model: model.invoke(prompt_for(topic)))

    print(response.text)
    print()
    print("response metadata:")
    print("  model:", response.response_metadata.get("model_name", active_model_name()))
    print("  tokens:", response.usage_metadata)


def run_temperature(topic: str) -> None:
    """
    Same prompt at three temperatures, to show the effect on variation.

    A new model is built for each value, because temperature is a constructor
    argument rather than something passed per call.
    """
    temperatures = (0.0, 0.7, 1.5)

    for index, temperature in enumerate(temperatures):
        response = run_with_fallback(
            lambda model: model.invoke(prompt_for(topic)), temperature=temperature
        )
        print(f"temperature={temperature}")
        print(str(response.text).strip())
        print()

        if index < len(temperatures) - 1:
            time.sleep(SECONDS_BETWEEN_CALLS)


def run_stream(topic: str) -> None:
    """
    stream() yields chunks as the model produces them, so the user sees output
    immediately instead of waiting for the whole response.
    """
    for chunk in stream_with_fallback(prompt_for(topic)):
        print(chunk.text, end="", flush=True)
    print()


def run_structured(topic: str) -> None:
    """
    with_structured_output() makes the model return a Joke object. This is more
    reliable than asking for JSON in the prompt and parsing the text yourself.

    Module 03 covers output parsers, which are the alternative for models that
    do not support this natively.
    """
    joke = run_with_fallback(
        lambda model: model.with_structured_output(Joke).invoke(prompt_for(topic))
    )

    print("setup:    ", joke.setup)
    print("punchline:", joke.punchline)
    print("rating:   ", joke.rating)


MODES = {
    "basic": run_basic,
    "temperature": run_temperature,
    "stream": run_stream,
    "structured": run_structured,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a joke about a topic.")
    parser.add_argument("topic", help="what the joke should be about")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="basic",
        help="which model behaviour to demonstrate (default: basic)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show the full traceback instead of a short message",
    )
    args = parser.parse_args()

    try:
        MODES[args.mode](args.topic)
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
