"""
Module 04 mini project: Story Generator.

Builds a short story from a topic in three linked steps:

    topic -> title -> story -> summary

and demonstrates how LangChain composes steps:

    chain   the pipeline written with LCEL, the | operator
    manual  the identical work written out by hand, for comparison

Each later step depends on the output of an earlier one, which is what makes
this a chain rather than three unrelated calls.

Costs three API calls per run.

Usage:
    python story_generator.py "a lighthouse keeper who is afraid of the dark"
    python story_generator.py "..." --mode manual
    python story_generator.py "..." --show-graph
    python story_generator.py --show-graph --dry-run
"""

import argparse
import sys
from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, describe_api_error, run_with_fallback

TITLE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "You name stories. Reply with the title only, no quotes, no explanation."),
        ("human", "Suggest a title for a short story about: {topic}"),
    ]
)

STORY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You write short fiction. Write {paragraphs} short paragraphs. "
            "Plain prose, no headings, no markdown.",
        ),
        ("human", 'Write a story called "{title}" about: {topic}'),
    ]
)

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "You summarise fiction in one sentence, under 30 words."),
        ("human", "Summarise this story:\n\n{story}"),
    ]
)


# straight and curly quote characters a model might wrap a title in
QUOTE_CHARACTERS = "\"'“”‘’"


def clean_title(title: str) -> str:
    """
    Tidy the model's title before it is used downstream.

    Models often wrap a title in quotes or add a trailing full stop despite
    being told not to. Fixing it here means the story prompt receives a clean
    value, rather than every later step having to cope with the mess.

    Two details that a naive implementation gets wrong:

    Order. Stripping once leaves '"Title".' as 'Title"', because the full stop
    sits outside the closing quote and protects it. Looping until nothing
    changes handles any order.

    Pairs. Stripping quote characters from both ends independently turns
    '"Nested \'Quotes\'"' into "Nested 'Quotes", eating a real apostrophe. Only
    removing quotes when both ends have one keeps the inner pair intact.
    """
    text = str(title).strip()

    previous = None
    while text != previous:
        previous = text
        text = text.strip().rstrip(".").strip()

        wrapped = (
            len(text) >= 2
            and text[0] in QUOTE_CHARACTERS
            and text[-1] in QUOTE_CHARACTERS
        )
        if wrapped:
            text = text[1:-1].strip()

    return text


def count_words(data: dict) -> int:
    return len(data["story"].split())


def build_chain(model):
    """
    The whole pipeline, built with LCEL.

    The | operator joins runnables into a RunnableSequence. Each of the three
    inner chains is the same shape: prompt | model | parser.

    RunnablePassthrough.assign adds a key to the dictionary flowing through the
    chain while keeping everything already in it. That is what lets the story
    step see both topic and title, and the summary step see the story.
    """
    parser = StrOutputParser()

    # RunnableLambda turns a plain python function into a chain step, so
    # ordinary code can sit between two model calls
    title_chain = TITLE_PROMPT | model | parser | RunnableLambda(clean_title)
    story_chain = STORY_PROMPT | model | parser
    summary_chain = SUMMARY_PROMPT | model | parser

    return (
        RunnablePassthrough.assign(title=title_chain)
        | RunnablePassthrough.assign(story=story_chain)
        | RunnablePassthrough.assign(summary=summary_chain)
        # a step that costs nothing, to show not every link calls a model
        | RunnablePassthrough.assign(word_count=RunnableLambda(count_words))
    )


def run_chain(topic: str, paragraphs: int) -> dict:
    """One invoke call runs all three steps in order."""
    return run_with_fallback(
        lambda model: build_chain(model).invoke(
            {"topic": topic, "paragraphs": paragraphs}
        ),
        temperature=0.8,
        max_output_tokens=900,
    )


def run_manual(topic: str, paragraphs: int) -> dict:
    """
    The same three steps written by hand.

    Compare this with build_chain. The work is identical. What LCEL removes is
    the plumbing: passing values between steps, and remembering to parse each
    response. What it costs is that the flow is less obvious to a reader who
    does not already know LCEL.
    """
    parser = StrOutputParser()

    def steps(model):
        title_message = model.invoke(TITLE_PROMPT.invoke({"topic": topic}))
        title = clean_title(parser.invoke(title_message))

        story_message = model.invoke(
            STORY_PROMPT.invoke(
                {"topic": topic, "title": title, "paragraphs": paragraphs}
            )
        )
        story = parser.invoke(story_message)

        summary_message = model.invoke(SUMMARY_PROMPT.invoke({"story": story}))
        summary = parser.invoke(summary_message)

        return {
            "topic": topic,
            "title": title,
            "story": story,
            "summary": summary,
            "word_count": len(story.split()),
        }

    return run_with_fallback(steps, temperature=0.8, max_output_tokens=900)


def show_result(result: dict) -> None:
    print(f"title: {result['title']}")
    print()
    print(result["story"].strip())
    print()
    print(f"summary: {result['summary'].strip()}")
    print(f"words:   {result['word_count']}")


def show_graph() -> None:
    """
    Print the chain structure without calling the model.

    Building a chain does not run it, so this is free. It is the quickest way
    to check that a chain is wired the way you think it is.
    """
    from common.models import build_model

    placeholder = build_model("placeholder", "unused-key")
    print(build_chain(placeholder).get_graph().draw_ascii())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a short story from a topic, in three chained steps."
    )
    parser.add_argument("topic", nargs="?", help="what the story is about")
    parser.add_argument(
        "--mode",
        choices=("chain", "manual"),
        default="chain",
        help="LCEL pipeline or the hand written equivalent (default: chain)",
    )
    parser.add_argument(
        "--paragraphs", type=int, default=3, help="how long the story should be"
    )
    parser.add_argument(
        "--show-graph",
        action="store_true",
        help="print the chain structure before running",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build the chain but make no API calls",
    )
    parser.add_argument("--debug", action="store_true", help="show the full traceback")
    args = parser.parse_args()

    if args.show_graph:
        show_graph()
        print()

    if args.dry_run:
        return 0

    if not args.topic:
        parser.error("a topic is required unless --dry-run is used")

    try:
        if args.mode == "chain":
            result = run_chain(args.topic, args.paragraphs)
        else:
            result = run_manual(args.topic, args.paragraphs)
        show_result(result)
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
