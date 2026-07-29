# Module 01 - Models

**Status:** complete. All four modes run against the live API.

## Goal

Learn how to call a chat model from LangChain and control its behaviour.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| Chat models | `build_model()`, every mode |
| Temperature | `--mode temperature` |
| Max output tokens | `build_model(max_output_tokens=...)` |
| Streaming | `--mode stream` |
| Structured output | `--mode structured` |

## Files

| File | Purpose |
|------|---------|
| `joke_generator.py` | The mini project. Four modes, one per topic. |
| `list_models.py` | Finds a model name that works with the API key. |

## Prerequisites

Complete the setup in the [root README](../README.md) first. `GOOGLE_API_KEY`
must be set in the `.env` file at the repository root.

## Running it

Activate the shared virtual environment, then from this folder:

```powershell
python joke_generator.py "space travel"
python joke_generator.py "space travel" --mode temperature
python joke_generator.py "space travel" --mode stream
python joke_generator.py "space travel" --mode structured
```

The topic can be anything. Quote it if it contains spaces. Add `--debug` to any
command to see a full traceback instead of a short error message.

## What each mode shows

### basic

A single `invoke()` call, plus the metadata that comes back with it.

```
Why did the astronaut break up with her boyfriend?

Because she just needed some space!

response metadata:
  model: gemini-3.5-flash
  tokens: {'input_tokens': 12, 'output_tokens': 18, 'total_tokens': 30, ...}
```

The point of this mode is that `invoke()` returns an `AIMessage` object, not a
string. The message carries the reply plus `response_metadata` and
`usage_metadata`, which is where token counts come from. Token counts are worth
watching from the start, because they are what you pay for.

### temperature

Sends the same prompt at temperature 0.0, 0.7 and 1.5.

- **0.0** is near deterministic. Use it for extraction, classification, or
  anything where the same input should give the same answer.
- **0.7** is a reasonable general purpose default.
- **1.5** is much more varied and more likely to drift off task.

Run this mode a few times. The 0.0 output should stay close to identical across
runs.

The effect is often less dramatic than expected, and it is worth understanding
why rather than assuming the setting is broken. In one run, 0.7 and 1.5 both
returned the same joke. Two reasons:

- The prompt is short and heavily constrained. There are only so many
  well known jokes about a given topic, so a handful of completions dominate the
  probability mass and stay on top even after temperature flattens it.
- Temperature affects sampling, not correctness. A high value does not make a
  model more creative in any useful sense, it makes it pick less likely tokens.

To see a clearer difference, ask for something with a larger space of valid
answers, such as a short story opening rather than a joke.

Note also that temperature 0.0 is not a guarantee of identical output across
runs, only a strong tendency toward it.

This mode makes three calls in a row, so it pauses a few seconds between them.
Without that pause the free tier rate limit rejects the later calls.

### stream

Uses `model.stream()`, which yields chunks as the model produces them rather
than waiting for the whole response. This is what makes a chatbot feel
responsive. The final text is identical to `basic`, only the timing differs.

### structured

Uses `with_structured_output(Joke)` where `Joke` is a Pydantic model.

```
setup:     A SQL query walks into a bar, walks up to two tables and asks...
punchline: "Can I join you?"
rating:    8
```

The return value is a real `Joke` object with typed, validated fields, not text
that looks like JSON.

Contrast this with the obvious alternative of asking for JSON in the prompt and
parsing the response yourself. That approach breaks when the model wraps the
JSON in a code fence, adds a sentence before it, or returns `"nine"` where an
integer was expected. Module 03 covers output parsers, which handle the cases
where you genuinely do have to parse text.

## Things that caused real problems

These are not hypothetical. Each one broke this project before it worked.

### Listed models are not always usable

`list_models.py` with no arguments prints what the API advertises. That list is
misleading on its own:

- `gemini-2.5-flash` is listed and returns **404** when called.
- `gemini-2.0-flash` is listed and returns **429 with a quota limit of 0**,
  meaning it has no free tier allocation at all. The error message says
  "you exceeded your current quota", which is misleading, since the real
  problem is that the quota was never greater than zero.
- Every Pro model reports zero free tier quota. On a free key, use `flash`.

`python list_models.py --probe` sends one tiny request to each candidate and
reports what actually happens, which is the only reliable way to choose.

### Thinking models

Current Gemini flash models run an internal reasoning step before answering, and
**those reasoning tokens count against `max_output_tokens`**.

With `max_output_tokens=256` and reasoning left on, a joke request produced:

```
tokens: {'output_tokens': 252, 'output_token_details': {'reasoning': 243}}
```

243 of 252 tokens were spent thinking. The joke was cut off before the
punchline, and `--mode structured` failed outright because nothing parseable was
left. Setting `thinking_budget=0` dropped the same request to 25 output tokens
and returned a complete joke.

A joke needs no reasoning, so it is switched off here. For a task that does
benefit from reasoning, leave it on and raise `max_output_tokens` instead.

### .content is not a string

In LangChain 1.x, `response.content` is a list of content blocks:

```
[{'type': 'text', 'text': 'How do you organize a space party?', 'extras': {...}}]
```

Printing it dumps internal structure, including a long base64 signature.
Use `response.text` instead, which joins the text blocks. It is a property, not
a method - calling `response.text()` still works but is deprecated.

Most tutorials predate this and use `.content` directly, because in 0.x it was
a plain string.

### Parameter naming

The parameter is `max_output_tokens`, not `max_tokens`. It caps the response,
not the input, and a response that hits the cap stops mid sentence rather than
raising an error, which makes it easy to misdiagnose.

## Other notes

- The API key is read from the environment, never written into the code. Every
  module follows this pattern.
- `temperature` and the model name are constructor arguments, so a differently
  configured model means a new instance. That is why `run_temperature` builds
  three models rather than reusing one.
- Errors are caught and explained by `describe_api_error()`. The raw provider
  error for a rate limit is roughly sixty lines of nested JSON and traceback
  with the useful sentence buried in the middle.

