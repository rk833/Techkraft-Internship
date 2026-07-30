# Module 11 - Agents

**Status:** complete. All three tools run against the live API.

## Goal

Hand control to the model. Everything before this ran a fixed pipeline written
in code; here the model decides which tools to call, with what arguments, and in
what order.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| Tool calling | `create_agent(tools=ALL_TOOLS)` |
| StructuredTool | `CalculatorInput`, via `args_schema` |
| Agent loop | `create_agent`, which builds a LangGraph loop |
| ReAct | what the loop implements, see below |

## Files

| File | Purpose |
|------|---------|
| `utility_agent.py` | The agent. Two commands. |
| `tools.py` | The three tools. Ordinary Python functions. |

## Setup

No API keys beyond the Gemini one. Both external services are free and need no
registration:

| Service | Used for | Key needed |
|---------|----------|-----------|
| Open-Meteo | weather and geocoding | none |
| Wikipedia REST API | factual lookups | none |

## Running it

```powershell
python utility_agent.py tools
python utility_agent.py ask --question "what is 18 * 4.5"
python utility_agent.py ask --question "who was Ada Lovelace, and what is 2 to the power of 10"
python utility_agent.py ask --question "what is the temperature in Kathmandu right now, and what is that in Fahrenheit"
python utility_agent.py ask --question "..." --quiet
```

**Cost:** `tools` makes no API call. `ask` costs **one chat call per turn of the
loop**, so a question needing two rounds of tool calls costs three calls: one to
decide, one to decide again after seeing results, one to write the answer. This
is the module where cost is hardest to predict, because the model decides how
many turns to take.

## What you should see

### One tool

```
question: what is 18 * 4.5

  calling calculator({'expression': '18 * 4.5'})
  -> 81

18 * 4.5 is 81.

[1 tool call(s), 4 messages in the loop]
```

Four messages: your question, the model asking for a tool, the tool result, the
final answer.

### Two tools at once

```
question: who was Ada Lovelace, and what is 2 to the power of 10

  calling wikipedia({'query': 'Ada Lovelace'})
  calling calculator({'expression': '2**10'})
  -> Ada Lovelace: Augusta Ada King, Countess of Lovelace, was an English...
  -> 1024

Ada Lovelace was an English mathematician and writer, widely considered the
first computer programmer... Two to the power of 10 is 1,024.

[2 tool call(s), 5 messages in the loop]
```

Both calls were issued **together**, before either result came back. The two
sub-questions are independent, so the model asked for both at once. That is
parallel tool calling, and it is why the loop only took one extra turn instead
of two.

### Two tools in sequence, where the second depends on the first

```
question: what is the temperature in Kathmandu right now, and what is that in Fahrenheit

  calling weather({'city': 'Kathmandu'})
  -> Kathmandu, Nepal: thunderstorm, 23.4 C, humidity 93%, wind 1.0 km/h
  calling calculator({'expression': '23.4 * 9 / 5 + 32'})
  -> 74.12

The current temperature in Kathmandu is 23.4 C, which is 74.12 F.

[2 tool call(s), 6 messages in the loop]
```

**This is the module in one output.** The model called `weather`, read `23.4 C`
out of a sentence of prose, worked out that Celsius to Fahrenheit is
`x * 9 / 5 + 32`, built that expression with the value substituted, and called
the calculator with it.

None of that is in the code. There is no conversion function, no rule saying
weather results can feed the calculator, and no ordering. The second call could
not be issued until the first returned, so the loop ran an extra turn on its
own.

## How it works

```python
agent = create_agent(model=model, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)
result = agent.invoke({"messages": [HumanMessage(content=question)]})
```

That is the whole agent. `create_agent` builds a loop:

```
send messages to the model
    did it ask for tools?
        yes -> run them, append the results, go round again
        no  -> that message is the answer
```

This pattern is **ReAct**, reason and act interleaved. Older tutorials implement
it by prompting the model to emit `Thought:` / `Action:` / `Observation:` text
and then parsing that text back out. Modern models have native tool calling, so
the structure comes back as data rather than prose that has to be scraped.
`create_agent` uses the native mechanism, which is why there is no output parser
here and no parsing errors to handle.

## The tool description is the prompt

Run `python utility_agent.py tools` to see exactly what the model receives:

```
name: calculator
description:
    Evaluate an arithmetic expression. Use this for any sum, however simple.
    Handles + - * / // % and ** with brackets. Does not handle words, units,
    currency symbols or variables, so pass digits and operators only.
arguments:
    expression (string): An arithmetic expression, for example '18 * 4.5'
```

**The model never sees the code.** Name, description and argument schema are its
entire manual, and all three are sent with every request. So:

- A vague docstring produces a tool that gets called at the wrong times.
- "Does not handle words, units, currency symbols" exists because without it the
  model passes `"$18 * 4.5"` or `"18 apples * 4.5"`.
- `CalculatorInput` gives the argument its own description, which is why the
  model reliably sends a bare expression.

Tool docstrings are prompt engineering, not documentation. This is the same
lesson as the Pydantic `Field` descriptions in Module 03, applied to a different
place.

## Do not use eval in a tool

The calculator could be one line:

```python
return str(eval(expression))   # do not do this
```

Tool arguments are written by a language model, often echoing something a user
typed, so they are untrusted input. `eval` runs whatever it is given:

```
__import__('os').system('...')
open('secret.txt').read()
```

Instead `expression` is parsed to a syntax tree and walked, allowing only
numbers and an allow-list of arithmetic operators. Anything else is refused
before it runs. Tested:

| Input | Result |
|-------|--------|
| `18 * 4.5` | `81` |
| `(120 - 15) / 7` | `15` |
| `1/0` | `error: division by zero` |
| `__import__('os').system('echo pwned')` | `error: unsupported expression element: Call` |
| `open('secret.txt').read()` | `error: unsupported expression element: Call` |
| `x + 1` | `error: unsupported expression element: Name` |

The refusal is structural, not a blocklist. There is no list of dangerous
function names to keep up to date, because function calls are simply not a thing
the evaluator can represent.

**Any tool an agent can reach is an entry point into your system.** A tool that
runs shell commands, writes files or issues SQL deserves more care than this
one, not less.

## Things that caused real problems

### The wikipedia PyPI package is broken

The obvious dependency for a Wikipedia tool fails on every call:

```
wikipedia lookup failed: Expecting value: line 1 column 1 (char 0)
```

That is a JSON parse error hiding the real cause. Calling the API directly shows
it:

```
status: 403
Please set a user-agent and respect our robot policy
```

**Wikipedia now returns 403 to any request without a User-Agent header.** The
`wikipedia` package was last updated in 2014 and does not send one, so it cannot
work regardless of how it is called.

The tool therefore calls the API directly with `requests` and a User-Agent, in
two steps: search for the best matching title, then fetch that page's summary.
That removed a dependency rather than adding one, and it is a reminder that a
tool is just a function - nothing required a library at all.

### Weather without an API key

The original outline assumed a weather API key. Open-Meteo needs no key, no
account and no card, and provides geocoding too, so a plain city name works.
It returns a WMO weather code rather than text, which `WEATHER_CODES` maps into
something readable before the model sees it.

### The agent over-calls tools

Asked "what is the capital of France", the agent called Wikipedia rather than
answering from its own knowledge. It was following the system prompt, which says
to use Wikipedia for factual background about places.

That costs a round trip and some latency for a question any model can answer.
The tension is real and has no clean answer:

- Encourage tools, and the agent uses them when it does not need to.
- Discourage them, and it answers from memory when it should have checked.

The arithmetic rule here is deliberately absolute - "use the calculator for
every arithmetic question, even easy ones" - because a model doing mental
arithmetic is right most of the time and wrong silently. For Wikipedia the same
firmness costs more than it gains. Worth experimenting with.

## Version note

`AgentExecutor`, `initialize_agent` and `create_react_agent` are gone from
`langchain.agents` in 1.x. `langchain.agents` now exports only `create_agent`,
`AgentState`, `middleware`, `factory` and `structured_output`.

The old names still exist in `langchain_classic.agents` if you need to read
older code, but `create_agent` is the current API and is built on LangGraph,
which Module 13 covers directly.


