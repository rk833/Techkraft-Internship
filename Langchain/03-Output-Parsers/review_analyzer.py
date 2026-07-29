"""
Module 03 mini project: Movie Review Analyzer.

Turns a free text film review into structured data, and demonstrates the three
output parsers.

    str       StrOutputParser, pulls the plain text out of the reply
    json      JsonOutputParser, returns a Python dict
    pydantic  PydanticOutputParser, returns a validated typed object

The interesting part is not the parsing itself but where the instructions come
from. Both json and pydantic generate their own format instructions from a
schema and inject them into the prompt. Use --show-prompt to see them.

Usage:
    python review_analyzer.py --file sample_review.txt
    python review_analyzer.py --file sample_review.txt --mode json
    python review_analyzer.py --file sample_review.txt --mode pydantic
    python review_analyzer.py --review "short review text here" --mode pydantic
    python review_analyzer.py --file sample_review.txt --mode pydantic --show-prompt
"""

import argparse
import json
import sys
from pathlib import Path

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import (
    JsonOutputParser,
    PydanticOutputParser,
    StrOutputParser,
)
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, describe_api_error, run_with_fallback


# Both parsers turn this class into format instructions, so everything in it is
# sent to the model as part of the prompt. That includes the docstring and every
# Field description, which is why they are written as instructions to the model
# rather than as notes to a reader. Keep them short: they cost input tokens on
# every single call.
class ReviewAnalysis(BaseModel):
    """Structured analysis of one film review."""

    sentiment: str = Field(description="one of: Positive, Negative, Mixed")
    rating: int = Field(description="overall rating from 1 to 10")
    themes: list[str] = Field(description="two to four short topic tags")
    praise: list[str] = Field(description="specific things the reviewer liked")
    criticism: list[str] = Field(description="specific things the reviewer disliked")
    summary: str = Field(description="one sentence summary, under 25 words")


def build_prompt(format_instructions: str) -> ChatPromptTemplate:
    """
    A prompt with a slot for parser generated format instructions.

    partial_variables fills that slot once, at build time, because the
    instructions come from the schema rather than from the user.
    """
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You analyse film reviews. Base every field only on what the "
                "review actually says, and never invent detail.\n"
                "{format_instructions}",
            ),
            ("human", "Review:\n{review}"),
        ]
    ).partial(format_instructions=format_instructions)


def parser_for(mode: str):
    """
    Pick the parser and the format instructions that go with it.

    StrOutputParser has no schema, so the prompt has to describe the wanted
    output in prose. That difference is the point of comparing the modes.
    """
    if mode == "str":
        return StrOutputParser(), (
            "Reply with a short plain text analysis covering sentiment, a rating "
            "out of 10, the main themes, what the reviewer praised, and what "
            "they criticised."
        )

    if mode == "json":
        parser = JsonOutputParser(pydantic_object=ReviewAnalysis)
        return parser, parser.get_format_instructions()

    parser = PydanticOutputParser(pydantic_object=ReviewAnalysis)
    return parser, parser.get_format_instructions()


def show_result(mode: str, result) -> None:
    """Print the parsed result, and make its Python type visible."""
    print(f"parsed type: {type(result).__name__}")
    print()

    if mode == "str":
        print(result.strip())
        return

    if mode == "json":
        # a plain dict, so keys are not guaranteed and values are not validated
        print(json.dumps(result, indent=2))
        return

    # a ReviewAnalysis instance, so attributes are typed and already checked
    print(f"sentiment:  {result.sentiment}")
    print(f"rating:     {result.rating}")
    print(f"themes:     {', '.join(result.themes)}")
    print(f"praise:     {'; '.join(result.praise)}")
    print(f"criticism:  {'; '.join(result.criticism)}")
    print(f"summary:    {result.summary}")


def run(mode: str, review: str, show_prompt: bool) -> None:
    parser, format_instructions = parser_for(mode)
    prompt = build_prompt(format_instructions)

    if show_prompt:
        print("prompt sent to the model:")
        for message in prompt.format_messages(review=review):
            print(f"[{message.type}] {message.content}")
        print()
        print("response:")

    filled = prompt.invoke({"review": review})

    # temperature 0.0 because this is extraction, not writing. the same review
    # should give the same analysis every time.
    response = run_with_fallback(lambda model: model.invoke(filled), temperature=0.0)

    try:
        result = parser.invoke(response)
    except OutputParserException as error:
        print("the model returned something the parser could not read.")
        print()
        print("raw reply:")
        print(str(response.text).strip())
        print()
        print(f"parser error: {str(error).splitlines()[0]}")
        raise SystemExit(1)

    show_result(mode, result)


def read_review(args) -> str:
    if args.review:
        return args.review

    path = Path(args.file)
    if not path.exists():
        raise ConfigError(f"review file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a free text film review into structured data."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--review", help="review text given directly")
    source.add_argument(
        "--file", default="sample_review.txt", help="path to a file holding the review"
    )
    parser.add_argument(
        "--mode",
        choices=("str", "json", "pydantic"),
        default="pydantic",
        help="which parser to use (default: pydantic)",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="print the rendered prompt, including the generated format instructions",
    )
    parser.add_argument(
        "--debug", action="store_true", help="show the full traceback"
    )
    args = parser.parse_args()

    try:
        run(args.mode, read_review(args), args.show_prompt)
    except ConfigError as error:
        print(error)
        return 1
    except SystemExit as error:
        return int(error.code or 0)
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
