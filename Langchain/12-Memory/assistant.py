"""
Module 12 mini project: Personal AI Assistant.

A chatbot that remembers earlier turns, and three different strategies for
deciding what "remembers" means.

    buffer   keep every message. perfect recall, cost grows every turn
    window   keep only the most recent messages. cheap, forgets the beginning
    summary  compress older turns into a summary, keep recent ones verbatim

The thing to understand first: the model is stateless. It has no memory of the
last request. "Memory" is nothing more than your code resending earlier messages
with every new question, which is why it costs tokens and why it has to be
managed at all.

    demo     replay a fixed conversation, so strategies can be compared
    chat     talk to it yourself
    threads  show two conversations kept apart, no API call

Usage:
    python assistant.py demo --strategy buffer
    python assistant.py demo --strategy window --window 4
    python assistant.py demo --strategy summary
    python assistant.py chat
    python assistant.py threads
"""

import argparse
import sys
from pathlib import Path

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    trim_messages,
)
from langchain_core.messages.utils import count_tokens_approximately

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_model_name, describe_api_error, run_with_fallback

SYSTEM_PROMPT = (
    "You are a friendly assistant. Keep answers to one or two short sentences."
)

# A fixed conversation, so the strategies can be compared on identical input.
# The first turn plants two facts and the last turn asks for them back, which
# is what makes forgetting visible.
SCRIPT = [
    "Hi, I'm Ridesha. I'm learning LangChain, and my favourite number is 17.",
    "What is a vector database, in one sentence?",
    "And what is an embedding? Briefly.",
    "What is my name, and what is my favourite number?",
]


class Memory:
    """
    Base strategy: hold the conversation and decide what to send.

    Every strategy stores the full history. They differ only in what
    messages_to_send returns, which is the part that costs money.
    """

    def __init__(self):
        self.history = []

    def add_user(self, text: str) -> None:
        self.history.append(HumanMessage(content=text))

    def add_ai(self, text: str) -> None:
        self.history.append(AIMessage(content=text))

    def messages_to_send(self) -> list:
        raise NotImplementedError


class BufferMemory(Memory):
    """
    Send everything.

    Perfect recall and the simplest thing that works. The problem is arithmetic:
    turn N resends all N-1 previous turns, so total tokens across a conversation
    grow with the square of its length. Fine for ten turns, ruinous for a
    thousand.
    """

    def messages_to_send(self) -> list:
        return list(self.history)


class WindowMemory(Memory):
    """
    Send only the most recent messages.

    Cost per turn stops growing, which is the point. The cost is that anything
    older than the window is simply gone, and the assistant has no way of
    knowing it ever existed.

    trim_messages does the cutting. strategy="last" keeps the end of the list,
    and include_system keeps the system prompt regardless, which matters
    because otherwise the assistant loses its instructions along with the
    history.
    """

    def __init__(self, window: int):
        super().__init__()
        self.window = window

    def messages_to_send(self) -> list:
        return trim_messages(
            self.history,
            max_tokens=self.window,
            token_counter=len,  # count messages, not tokens, so it is easy to see
            strategy="last",
            include_system=False,
            start_on="human",
        )


class SummaryMemory(Memory):
    """
    Compress older turns into a summary, keep recent turns verbatim.

    A middle path: cost stays bounded like a window, but nothing is lost
    outright, because the older material survives in compressed form.

    The trade is that summarising costs an extra model call whenever it
    triggers, and a summary is lossy. Details the summariser judged
    unimportant are gone for good, so the choice of summary prompt matters.
    """

    def __init__(self, keep: int, trigger: int):
        super().__init__()
        self.keep = keep
        self.trigger = trigger
        self.summary = ""

    def maybe_summarise(self) -> bool:
        """Fold everything except the last few messages into the summary."""
        if len(self.history) <= self.trigger:
            return False

        older = self.history[: -self.keep]
        recent = self.history[-self.keep :]

        transcript = "\n".join(
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.text}"
            for m in older
        )
        instruction = (
            "Summarise this conversation in under 80 words. Keep every concrete "
            "fact the user stated about themselves, including names, numbers and "
            "preferences, even if they seem trivial.\n\n"
        )
        if self.summary:
            instruction += f"Summary so far:\n{self.summary}\n\n"
        instruction += f"New messages:\n{transcript}"

        response = run_with_fallback(
            lambda model: model.invoke([HumanMessage(content=instruction)]),
            temperature=0.0,
        )
        self.summary = str(response.text).strip()
        self.history = recent
        return True

    def messages_to_send(self) -> list:
        if not self.summary:
            return list(self.history)
        note = SystemMessage(
            content=f"Summary of the earlier conversation:\n{self.summary}"
        )
        return [note] + list(self.history)


def build_memory(strategy: str, window: int) -> Memory:
    if strategy == "buffer":
        return BufferMemory()
    if strategy == "window":
        return WindowMemory(window)
    return SummaryMemory(keep=2, trigger=4)


def reply(memory: Memory, question: str) -> tuple:
    """
    One turn.

    The system prompt is prepended on every call. It is not stored in history,
    because it is configuration rather than conversation.
    """
    memory.add_user(question)
    sent = [SystemMessage(content=SYSTEM_PROMPT)] + memory.messages_to_send()

    response = run_with_fallback(
        lambda model: model.invoke(sent), temperature=0.3, max_output_tokens=200
    )
    answer = str(response.text).strip()
    memory.add_ai(answer)

    return answer, len(sent), count_tokens_approximately(sent)


def demo(strategy: str, window: int) -> None:
    memory = build_memory(strategy, window)

    print(f"strategy: {strategy}" + (f" (window {window} messages)" if strategy == "window" else ""))
    print()

    for turn, question in enumerate(SCRIPT, start=1):
        if isinstance(memory, SummaryMemory) and memory.maybe_summarise():
            print(f"  [summarised older turns into {len(memory.summary)} chars]")

        answer, count, tokens = reply(memory, question)

        print(f"turn {turn}  (sent {count} messages, ~{tokens} tokens)")
        print(f"  you: {question}")
        print(f"  bot: {answer}")
        print()

    print("the last question can only be answered from turn 1.")
    if strategy == "window":
        print("with a small window those messages were dropped before it was asked.")


def chat(strategy: str, window: int) -> None:
    memory = build_memory(strategy, window)
    print(f"strategy: {strategy}. type 'exit' to stop, 'stats' for message counts.")
    print()

    while True:
        try:
            question = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            return
        if question.lower() == "stats":
            sending = memory.messages_to_send()
            print(
                f"     stored {len(memory.history)} messages, "
                f"sending {len(sending)}, ~{count_tokens_approximately(sending)} tokens"
            )
            continue

        if isinstance(memory, SummaryMemory) and memory.maybe_summarise():
            print("     [summarised older turns]")

        answer, count, tokens = reply(memory, question)
        print(f"bot: {answer}")
        print(f"     [sent {count} messages, ~{tokens} tokens]")


def threads() -> None:
    """
    Two conversations kept apart, with no API calls.

    Memory is per conversation, not global. Every real assistant needs a key to
    separate them, usually a user or session id. LangGraph calls this a
    thread_id; here it is just a dictionary key, which is all it ever really is.
    """
    conversations = {}
    for thread, text in [
        ("alice", "My favourite number is 17."),
        ("bob", "My favourite number is 4."),
        ("alice", "What did I say my favourite number was?"),
    ]:
        conversations.setdefault(thread, BufferMemory()).add_user(text)
        print(f"[{thread}] {text}")

    print()
    for thread, memory in conversations.items():
        print(f"{thread}: {len(memory.history)} messages stored")
        for message in memory.messages_to_send():
            print(f"    {message.text}")

    print()
    print("alice's history never contains bob's number. without a key like this")
    print("every user would share one conversation.")


def main() -> int:
    parser = argparse.ArgumentParser(description="A chatbot that remembers.")
    parser.add_argument("command", choices=("demo", "chat", "threads"))
    parser.add_argument(
        "--strategy", choices=("buffer", "window", "summary"), default="buffer"
    )
    parser.add_argument(
        "--window", type=int, default=4, help="messages kept by the window strategy"
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "demo":
            demo(args.strategy, args.window)
        elif args.command == "chat":
            chat(args.strategy, args.window)
        else:
            threads()
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
