"""
Module 13 mini project: Research Workflow.

    question -> research -> summarize -> review -> final answer
                                 ^          |
                                 +--revise--+

A graph rather than a chain, because of that arrow going backwards. A chain runs
each step once in a fixed order. A graph can decide where to go next, and can
send work back to an earlier step. The review node judges the summary and either
approves it or returns it with feedback to be rewritten.

    show   print the graph structure, no API calls
    run    execute the workflow, printing each node as it fires

Nodes are ordinary functions. Each receives the state and returns the keys it
wants to change. LangGraph merges that into the state and works out what runs
next.

Usage:
    python research_workflow.py show
    python research_workflow.py run --question "What was the Analytical Engine?"
    python research_workflow.py run --question "..." --strict
    python research_workflow.py run --question "..." --max-revisions 3
"""

import argparse
import sys
from pathlib import Path
from typing import TypedDict

import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, describe_api_error, run_with_fallback

WIKIPEDIA_HEADERS = {"User-Agent": "LangChainLearning/1.0 (educational project)"}
REQUEST_TIMEOUT = 20


class ResearchState(TypedDict):
    """
    Everything the workflow knows.

    One dictionary passed from node to node. Each node reads what it needs and
    returns only the keys it changed, so the state accumulates as the run
    progresses rather than being rebuilt each step.
    """

    question: str
    research: str
    summary: str
    approved: bool
    feedback: str
    revisions: int
    max_revisions: int
    strict: bool
    force_revisions: int
    answer: str


class Review(BaseModel):
    """The reviewer's verdict, as data rather than prose."""

    approved: bool = Field(description="true if the summary is good enough to send")
    feedback: str = Field(
        description="if not approved, one sentence saying exactly what to fix"
    )


def research(state: ResearchState) -> dict:
    """
    Gather source material from Wikipedia.

    A node does not have to call a model. This one is plain HTTP, which is
    worth noticing: the graph coordinates steps, it does not care what they do.
    """
    question = state["question"]
    try:
        found = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": question,
                "srlimit": 2,
                "format": "json",
            },
            headers=WIKIPEDIA_HEADERS,
            timeout=REQUEST_TIMEOUT,
        ).json()
    except requests.RequestException as error:
        return {"research": f"research failed: {error}"}

    hits = found.get("query", {}).get("search", [])
    if not hits:
        return {"research": "no sources found"}

    extracts = []
    for hit in hits:
        title = hit["title"]
        try:
            summary = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + requests.utils.quote(title, safe=""),
                headers=WIKIPEDIA_HEADERS,
                timeout=REQUEST_TIMEOUT,
            ).json()
        except requests.RequestException:
            continue
        if summary.get("extract"):
            extracts.append(f"{title}: {summary['extract']}")

    return {"research": "\n\n".join(extracts) or "no usable sources found"}


def summarize(state: ResearchState) -> dict:
    """
    Write the answer from the research.

    On a revision the reviewer's feedback is added to the prompt, which is the
    only reason looping back is useful. Without it the node would produce the
    same output again and the graph would spin.
    """
    instruction = (
        f"Question: {state['question']}\n\n"
        f"Source material:\n{state['research']}\n\n"
        "Answer the question in three or four sentences, using only the source "
        "material above. Plain prose, no headings."
    )

    if state.get("feedback"):
        instruction += (
            f"\n\nA previous attempt was rejected for this reason:\n"
            f"{state['feedback']}\n"
            f"Previous attempt:\n{state['summary']}\n"
            f"Write a better version that fixes it."
        )

    response = run_with_fallback(
        lambda model: model.invoke([HumanMessage(content=instruction)]),
        temperature=0.3,
        max_output_tokens=400,
    )
    return {"summary": str(response.text).strip()}


def review(state: ResearchState) -> dict:
    """
    Judge the summary, returning a typed verdict.

    with_structured_output from Module 01 is what makes the routing possible.
    A prose review would have to be parsed to decide where to go next, and a
    routing decision made by string matching is a routing decision that breaks.
    """
    # Demo aid. A good model approves a good summary first time, so the loop
    # never fires and the most interesting edge in the graph goes untested.
    # This rejects the first N attempts outright, and costs no API call,
    # because no model is asked.
    if state["revisions"] < state["force_revisions"]:
        return {
            "approved": False,
            "feedback": (
                "Forced revision for demonstration. Make the answer more "
                "specific and mention the date it was first described."
            ),
            "revisions": state["revisions"] + 1,
        }

    bar = (
        "Be demanding. Reject the summary unless it is genuinely excellent: "
        "specific, complete and well written."
        if state["strict"]
        else "Approve the summary if it answers the question and is supported by "
        "the source material."
    )

    instruction = (
        f"{bar}\n\n"
        f"Question: {state['question']}\n\n"
        f"Source material:\n{state['research']}\n\n"
        f"Summary to review:\n{state['summary']}\n\n"
        "Reject it if it contains anything not supported by the source material, "
        "misses the point of the question, or is longer than four sentences."
    )

    verdict = run_with_fallback(
        lambda model: model.with_structured_output(Review).invoke(
            [HumanMessage(content=instruction)]
        ),
        temperature=0.0,
    )
    return {
        "approved": verdict.approved,
        "feedback": verdict.feedback,
        "revisions": state["revisions"] + 1,
    }


def finalize(state: ResearchState) -> dict:
    """Assemble the answer. No model call, so this node is free."""
    note = "" if state["approved"] else " (returned unapproved, revision limit reached)"
    return {"answer": state["summary"] + note}


def route_after_review(state: ResearchState) -> str:
    """
    The conditional edge.

    Returns the name of the next node. This is the only place the graph can go
    backwards, and the revision cap is what keeps it from cycling forever.
    A graph with a cycle and no exit condition is an infinite loop with extra
    steps.
    """
    if state["approved"]:
        return "finalize"
    if state["revisions"] >= state["max_revisions"]:
        return "finalize"
    return "summarize"


def build_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("research", research)
    graph.add_node("summarize", summarize)
    graph.add_node("review", review)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "research")
    graph.add_edge("research", "summarize")
    graph.add_edge("summarize", "review")

    # the only branch in the graph. everything else runs in a fixed order.
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"summarize": "summarize", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    return graph.compile()


def show() -> None:
    """Print the structure. Compiling a graph does not run it, so this is free."""
    structure = build_graph().get_graph()
    print(structure.draw_ascii())

    # The ascii drawing lays nodes out top to bottom and does not make the
    # backwards edge obvious, so the edges are listed as well.
    print()
    print("edges:")
    for edge in structure.edges:
        arrow = "..>" if edge.conditional else "-->"
        print(f"  {edge.source:<10} {arrow} {edge.target}")

    print()
    print("review ..> summarize is the edge that matters. it points backwards,")
    print("to a node that has already run. a chain cannot express that.")
    print("no API calls were made.")


def run(question: str, max_revisions: int, strict: bool, force_revisions: int) -> None:
    app = build_graph()

    initial: ResearchState = {
        "question": question,
        "research": "",
        "summary": "",
        "approved": False,
        "feedback": "",
        "revisions": 0,
        "max_revisions": max_revisions,
        "strict": strict,
        "force_revisions": force_revisions,
        "answer": "",
    }

    print(f"question: {question}")
    print(
        f"mode: {'strict' if strict else 'normal'}, max revisions: {max_revisions}"
        + (f", forcing {force_revisions} revision(s)" if force_revisions else "")
    )
    print()

    # stream() yields the state after each node, which makes the path through
    # the graph visible instead of only the final result
    final = {}
    for step in app.stream(initial):
        for node, update in step.items():
            final.update(update)
            describe(node, update)

    print()
    print("final answer:")
    print(final.get("answer", "").strip())


def describe(node: str, update: dict) -> None:
    if node == "research":
        text = update.get("research", "")
        print(f"[research]  gathered {len(text)} characters of source material")
    elif node == "summarize":
        print(f"[summarize] wrote {len(update.get('summary', '').split())} words")
    elif node == "review":
        verdict = "approved" if update.get("approved") else "rejected"
        print(f"[review]    {verdict} (attempt {update.get('revisions')})")
        if not update.get("approved") and update.get("feedback"):
            print(f"            feedback: {update['feedback']}")
    elif node == "finalize":
        print("[finalize]  assembled the answer, no model call")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="A research workflow built as a LangGraph state graph."
    )
    parser.add_argument("command", choices=("show", "run"))
    parser.add_argument("--question", help="what to research")
    parser.add_argument(
        "--max-revisions", type=int, default=2, help="how many rewrites are allowed"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="raise the reviewer's bar, so revisions actually happen",
    )
    parser.add_argument(
        "--force-revisions",
        type=int,
        default=0,
        help="reject the first N attempts outright, to exercise the loop",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "show":
            show()
        else:
            if not args.question:
                parser.error("run needs --question")
            run(args.question, args.max_revisions, args.strict, args.force_revisions)
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
