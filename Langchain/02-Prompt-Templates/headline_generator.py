"""
Module 02 mini project: LinkedIn Headline Generator.

Generates professional LinkedIn headlines from a person's skills and career
goal, and demonstrates the three ways to build a prompt in LangChain:

    simple   PromptTemplate, a single string with placeholders
    chat     ChatPromptTemplate, a list of role tagged messages
    fewshot  ChatPromptTemplate with worked examples in front of the request

Use --show-prompt with any mode to print what is actually sent to the model.
Seeing the rendered prompt is the point of this module, and it costs nothing.

Usage:
    python headline_generator.py --skills "python, sql" --goal "move into data engineering"
    python headline_generator.py --skills "..." --goal "..." --mode chat
    python headline_generator.py --skills "..." --goal "..." --mode fewshot
    python headline_generator.py --skills "..." --goal "..." --show-prompt
"""

import argparse
import sys
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, describe_api_error, run_with_fallback

# Worked examples for the few-shot mode. These teach the model a house style:
# short, role first, pipe separated, no hype. They are deliberately unrelated to
# any particular user so the style transfers rather than the content.
FEWSHOT_EXAMPLES = [
    {
        "skills": "java, spring boot, postgresql",
        "goal": "move from support into backend development",
        "headline": "Backend Developer | Java, Spring Boot, PostgreSQL | Building reliable APIs",
    },
    {
        "skills": "figma, user research, prototyping",
        "goal": "join a product design team",
        "headline": "Product Designer | Figma, User Research, Prototyping | Designing for clarity",
    },
]


def build_simple_prompt() -> PromptTemplate:
    """
    PromptTemplate builds one string. The model receives no role information,
    so instructions and request are mixed together in a single block of text.
    """
    return PromptTemplate.from_template(
        "Write {count} LinkedIn headline options for a professional.\n"
        "Skills: {skills}\n"
        "Career goal: {goal}\n"
        "Each headline must be under 120 characters.\n"
        "Return them as a numbered list and nothing else."
    )


def build_chat_prompt() -> ChatPromptTemplate:
    """
    ChatPromptTemplate builds a list of role tagged messages.

    The standing instructions go in the system message and the specific request
    in the human message. This separation is what chat models are trained on,
    so it generally follows instructions more reliably than the same text
    flattened into one string.
    """
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a career coach who writes LinkedIn headlines.\n"
                "Rules: under 120 characters, no emojis, no buzzwords such as "
                "guru or ninja, and never invent experience the person did not "
                "mention.\n"
                "Return a numbered list and nothing else.",
            ),
            (
                "human",
                "Write {count} headline options.\nSkills: {skills}\nCareer goal: {goal}",
            ),
        ]
    )


def build_fewshot_prompt() -> ChatPromptTemplate:
    """
    Few-shot prompting: show the model worked examples before the real request.

    The examples are inserted as alternating human and ai turns, so the model
    sees a short conversation it should continue in the same style. This
    controls format and tone far more precisely than describing them in words.
    """
    example_turns = []
    for example in FEWSHOT_EXAMPLES:
        example_turns.append(
            ("human", f"Skills: {example['skills']}\nCareer goal: {example['goal']}")
        )
        example_turns.append(("ai", example["headline"]))

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a career coach who writes LinkedIn headlines.\n"
                "Match the style of the examples exactly.",
            ),
            *example_turns,
            ("human", "Skills: {skills}\nCareer goal: {goal}"),
        ]
    )


def render(prompt, values: dict) -> str:
    """Show the fully substituted prompt, with roles when there are any."""
    if isinstance(prompt, PromptTemplate):
        return prompt.format(**values)

    lines = []
    for message in prompt.format_messages(**values):
        lines.append(f"[{message.type}] {message.content}")
    return "\n".join(lines)


def run(mode: str, skills: str, goal: str, count: int, show_prompt: bool) -> None:
    if mode == "simple":
        prompt = build_simple_prompt()
        values = {"skills": skills, "goal": goal, "count": count}
    elif mode == "chat":
        prompt = build_chat_prompt()
        values = {"skills": skills, "goal": goal, "count": count}
    else:
        # the few-shot examples carry one headline each, so count is not used
        prompt = build_fewshot_prompt()
        values = {"skills": skills, "goal": goal}

    if show_prompt:
        print("prompt sent to the model:")
        print(render(prompt, values))
        print()
        print("response:")

    # invoke() on a prompt returns the filled prompt, which is then passed to
    # the model. Module 04 replaces these two steps with a single chain.
    filled = prompt.invoke(values)
    response = run_with_fallback(lambda model: model.invoke(filled))

    print(str(response.text).strip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate LinkedIn headlines from skills and a career goal."
    )
    parser.add_argument("--skills", required=True, help="comma separated skills")
    parser.add_argument("--goal", required=True, help="what the person is aiming for")
    parser.add_argument(
        "--mode",
        choices=("simple", "chat", "fewshot"),
        default="simple",
        help="which prompt style to use (default: simple)",
    )
    parser.add_argument(
        "--count", type=int, default=3, help="how many headlines to ask for"
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="print the rendered prompt before sending it",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show the full traceback instead of a short message",
    )
    args = parser.parse_args()

    try:
        run(args.mode, args.skills, args.goal, args.count, args.show_prompt)
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
