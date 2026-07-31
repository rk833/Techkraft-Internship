# Module 12 - Memory

**Status:** complete. All three strategies run against the live API.

## Goal

Make an assistant remember earlier turns, and understand what that costs.

## Topics covered

| Topic | Strategy |
|-------|----------|
| Buffer memory | `--strategy buffer` |
| Summary memory | `--strategy summary` |
| Chat history | `Memory.history`, in every strategy |
| Trimming | `trim_messages`, in `--strategy window` |

## Files

| File | Purpose |
|------|---------|
| `assistant.py` | The mini project. Three strategies, three commands. |

## Running it

```powershell
python assistant.py threads
python assistant.py demo --strategy buffer
python assistant.py demo --strategy window --window 4
python assistant.py demo --strategy summary
python assistant.py chat
```

| Command | Cost |
|---------|------|
| `threads` | none |
| `demo` | 4 calls, one per scripted turn, plus 1 if summarisation triggers |
| `chat` | 1 call per message you send |

`demo` replays a fixed four turn conversation so the strategies can be compared
on identical input. The first turn plants two facts, the last turn asks for them
back, which is what makes forgetting visible.

In `chat`, type `stats` to see how many messages are being sent, or `exit` to
stop.

## The idea this module rests on

**The model is stateless.** It remembers nothing between requests. Every LangChain
memory class, every chatbot you have used, works the same way: your code keeps a
list of messages and resends them with each new question.

That single fact explains everything else here. Memory costs tokens because it
is re-uploaded every turn. Memory has strategies because that cost grows. There
is no server-side conversation to manage.

## What you should see

### buffer

```
turn 1  (sent 2 messages, ~45 tokens)
  you: Hi, I'm Ridesha. I'm learning LangChain, and my favourite number is 17.
turn 2  (sent 4 messages, ~93 tokens)
turn 3  (sent 6 messages, ~149 tokens)
turn 4  (sent 8 messages, ~208 tokens)
  you: What is my name, and what is my favourite number?
  bot: Your name is Ridesha, and your favorite number is 17.
```

It remembers, and **watch the token count**: 45, 93, 149, 208. Every turn
resends everything before it.

That growth is quadratic in the length of the conversation, not linear. Turn 50
resends 49 turns; the total tokens spent across a conversation of N turns scales
with N squared. Fine for ten turns, ruinous for a thousand.

### window

```
turn 1  (sent 2 messages, ~45 tokens)
turn 2  (sent 4 messages, ~93 tokens)
turn 3  (sent 4 messages, ~94 tokens)
turn 4  (sent 4 messages, ~92 tokens)
  you: What is my name, and what is my favourite number?
  bot: I don't know your name or your favorite number, as I don't have
       access to your personal information.
```

**Cost stops growing.** 45, 93, 94, 92, flat from turn 2 onward, and it would
stay flat over a thousand turns.

**And it forgot.** The name was in turn 1, which fell out of the window before
turn 4 was asked. Note how it answers: not "I have forgotten" but "I don't have
access to your personal information". It does not know that anything is missing,
because from its point of view the conversation began two messages ago.

That is the trade in one screen. Bounded cost, unbounded forgetting.

### summary

```
turn 3  (sent 6 messages, ~149 tokens)
  [summarised older turns into 342 chars]
turn 4  (sent 5 messages, ~195 tokens)
  bot: Your name is Ridesha, and your favorite number is 17.
```

It remembered, from the summary rather than the original message, and the
summary prompt is why:

> Keep every concrete fact the user stated about themselves, including names,
> numbers and preferences, even if they seem trivial.

Without that line a summariser writes "the user introduced themselves and asked
about vector databases", which is a perfectly good summary that loses exactly
what was needed.

## The honest comparison

| Strategy | Tokens at turn 4 | Remembered? | API calls |
|----------|-----------------|-------------|-----------|
| buffer | 208 | yes | 4 |
| window | 92 | **no** | 4 |
| summary | 195 | yes | **5** |

**On this conversation, summarisation was not worth it.** It saved 13 tokens
against buffer, about 6 percent, and cost an extra API call to produce the
summary. Net loss.

That is not a flaw in the demo, it is the actual shape of the trade. Summarising
replaces N messages with a summary, so it only pays when N is large and the
summary is much shorter than what it replaced. Here four short messages became a
342 character summary, which is barely a saving.

Summarisation starts winning somewhere around dozens of turns, and wins heavily
at hundreds. Below that, buffer is simpler and cheaper. **Do not reach for
summary memory because it sounds sophisticated. Count the tokens.**

## Conversations have to be kept apart

```powershell
python assistant.py threads
```

```
alice: 2 messages stored
    My favourite number is 17.
    What did I say my favourite number was?
bob: 1 messages stored
    My favourite number is 4.
```

Memory is per conversation, not global. Without a key separating them, every
user of a deployed assistant shares one history, which is both a correctness bug
and a data leak.

LangGraph calls this key a `thread_id`. Here it is a dictionary key, which is
all it fundamentally is. What a framework adds is persistence, so the history
survives a restart, and here it does not: everything is in memory and gone when
the process exits.

## Version note, and why this module looks different

The classic tutorial answer is:

```python
from langchain.memory import ConversationBufferMemory   # gone in 1.x
from langchain.chains import ConversationChain          # gone in 1.x
```

Neither exists in `langchain` 1.x. They survive in `langchain_classic.memory`
and `langchain_classic.chains`, deprecated. Anything you find teaching
`ConversationChain` predates this version.

The current options are:

| Approach | Where |
|----------|-------|
| Do it yourself with a message list | this module |
| `trim_messages` | `langchain_core.messages` |
| Summarisation as agent middleware | `langchain.agents.middleware.SummarizationMiddleware` |
| Persisted history, thread ids | LangGraph checkpointers, `InMemorySaver` and friends |

**This module implements the strategies by hand on purpose.** `create_agent` with
a checkpointer would be about six lines and would teach nothing, because the
interesting part, deciding what to resend, would be inside the framework.
Writing `messages_to_send` explicitly makes it obvious that memory is a list and
a policy, nothing more.

`SummarizationMiddleware` is the production answer once the idea is clear. It
takes triggers like `("messages", 50)` or `("tokens", 3000)` and does what
`SummaryMemory` does here.

## Things worth knowing

### The system prompt is not history

```python
sent = [SystemMessage(content=SYSTEM_PROMPT)] + memory.messages_to_send()
```

It is prepended on every call but never stored in `history`. If it lived in the
history, a window strategy would eventually trim the assistant's own
instructions away.

`trim_messages` has an `include_system` flag for the case where the system
message is in the list. Keeping it out of the list entirely avoids the question.

### trim_messages counts whatever you tell it to

```python
trim_messages(self.history, max_tokens=self.window, token_counter=len, strategy="last")
```

`token_counter=len` counts **messages**, not tokens, which makes the window easy
to reason about in a demo. In production pass a real token counter, since a
window of 20 messages could be 200 tokens or 20,000.

`start_on="human"` prevents the trimmed list starting with an assistant reply to
a question that is no longer there, which confuses models.

### Token counts here are approximate

`count_tokens_approximately` estimates without an API call, which is the point.
Exact counts need the provider's tokeniser. The numbers are for comparing
strategies, not for billing.

