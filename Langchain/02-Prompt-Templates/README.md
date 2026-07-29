# Module 02 - Prompt Templates

**Status:** complete. All three modes run against the live API.

## Goal

Learn how to build prompts properly: with placeholders, with message roles, and
with worked examples.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| PromptTemplate | `--mode simple` |
| ChatPromptTemplate | `--mode chat` |
| Variables | all modes, via `{skills}`, `{goal}`, `{count}` |
| Few-shot prompting | `--mode fewshot` |

## Files

| File | Purpose |
|------|---------|
| `headline_generator.py` | The mini project. Three prompt styles, same task. |

## Prerequisites

Complete the setup in the [root README](../README.md) first.

## Running it

```powershell
python headline_generator.py --skills "python, sql, airflow" --goal "move into data engineering"
python headline_generator.py --skills "..." --goal "..." --mode chat
python headline_generator.py --skills "..." --goal "..." --mode fewshot
python headline_generator.py --skills "..." --goal "..." --show-prompt
```

| Flag | Meaning |
|------|---------|
| `--skills` | comma separated skills, required |
| `--goal` | what the person is aiming for, required |
| `--mode` | `simple`, `chat` or `fewshot` (default `simple`) |
| `--count` | how many headlines to ask for (default 3, ignored by `fewshot`) |
| `--show-prompt` | print the rendered prompt before sending it |
| `--debug` | show the full traceback instead of a short message |

**Use `--show-prompt` often.** Seeing exactly what reaches the model is the
whole point of this module, and it is the fastest way to debug a prompt that
behaves oddly.

## The three modes compared

All three were given the same input: skills `python, sql, airflow`, goal
`move into data engineering`. The differences below are real output.

### simple - PromptTemplate

Builds a single string with placeholders filled in.

```
1. Aspiring Data Engineer | Python, SQL & Airflow Enthusiast | Building Scalable Data Pipelines
2. Data Engineer | Python | SQL | Airflow | Transforming Data into Actionable Insights
3. Data Engineering Professional | Python, SQL & Airflow Specialist | Passionate about Data Architecture
```

Usable, but wordy. Note "Enthusiast", "Passionate about", "Transforming Data
into Actionable Insights" - the model reached for filler because nothing told it
not to.

`PromptTemplate` sends one undifferentiated block of text. The model gets no
signal about which part is a standing instruction and which part is the request.

### chat - ChatPromptTemplate

Splits the prompt into role tagged messages: a `system` message with the rules,
a `human` message with the request.

```
1. Data Engineer | Python | SQL | Airflow
2. Aspiring Data Engineer | Python | SQL | Airflow
3. Data Engineer | Building Scalable Data Pipelines with Python, SQL, and Airflow
```

Tighter, because the system message carried an explicit no-buzzwords rule and
the model actually followed it. Chat models are trained on this role structure,
so instructions placed in a system message tend to hold better than the same
words buried in a paragraph.

This is the format you should reach for by default.

### fewshot - examples instead of instructions

Puts two worked examples in front of the request as alternating human and ai
turns, so the model sees a short conversation to continue.

```
Data Engineer | Python, SQL, Airflow | Building scalable data pipelines
```

Exactly the house style of the examples: `Role | Skills | Short tagline`,
lowercase tagline, no filler. No rule in the system message described that
format. The examples did it.

**This is the main lesson of the module.** Describing a format in words is
unreliable. Showing two examples of it is precise. When a prompt keeps producing
almost-right formatting, adding examples usually beats adding more rules.

Run all three with `--show-prompt` and compare the structures side by side.

## How the few-shot prompt is built

```python
example_turns = []
for example in FEWSHOT_EXAMPLES:
    example_turns.append(("human", f"Skills: {example['skills']}\n..."))
    example_turns.append(("ai", example["headline"]))

ChatPromptTemplate.from_messages([
    ("system", "..."),
    *example_turns,
    ("human", "Skills: {skills}\nCareer goal: {goal}"),
])
```

The examples are fake prior turns of the conversation. The model does not know
they did not happen, and continues the pattern.

Two things to watch:

- **Examples cost input tokens on every call.** Two are usually enough. Ten
  rarely help enough to justify the cost.
- **Keep examples unrelated to the real input.** The ones here are a backend
  developer and a product designer, deliberately nothing like a data engineer,
  so the model copies the style rather than the content.

LangChain also provides `FewShotChatMessagePromptTemplate` for this. It is
useful when examples are selected dynamically, for instance picking the most
similar examples from a larger set. Building the turns directly, as here, is
clearer while the set is fixed and small.

## Why prompt and model are invoked separately

```python
filled = prompt.invoke(values)
response = build_model().invoke(filled)
```

Two explicit steps, so it is obvious that a prompt template is just a rendering
step that produces messages, and the model is a separate call.

Module 04 replaces this with a chain, `prompt | model | parser`, which is how it
would normally be written. The split here is for clarity, not because chaining
is unavailable.

## Things that caused real problems

### The free tier is 20 requests per day, per model

Not per minute. The exact quota is
`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, value **20**.

Testing this module exhausted `gemini-3.5-flash` for the day. The useful detail
is that the cap is **per model**, so switching `GEMINI_MODEL` in `.env` to
another usable model gives a fresh 20 immediately. Otherwise it resets at
midnight Pacific time.

This matters for how you work: prefer `--show-prompt` and offline rendering
while iterating on prompt wording, and only spend calls once the prompt looks
right.

### thinking_budget is not supported everywhere

Module 01 sets `thinking_budget=0` to stop reasoning tokens eating the output
budget. That parameter is not universally accepted:

| Model | `thinking_budget=0` | Notes |
|-------|---------------------|-------|
| `gemini-3.5-flash` | accepted | reasons heavily without it |
| `gemini-3.1-flash-lite` | accepted | does not reason either way |
| `gemini-3-flash-preview` | accepted | 118 reasoning tokens without it |
| `gemini-3.5-flash-lite` | **400 error** | does not reason anyway, so no loss |
| `gemini-3.6-flash` | **400 error** | also ignores `temperature` |
| `gemma-4-31b-it` | **400 error** | "Thinking budget is not supported" |

It is now controlled by `GEMINI_THINKING_BUDGET` in `.env`. Leave it empty to
stop sending the parameter. Hardcoding it, as the first version of Module 01
did, silently tied the code to a subset of models.

Also note `gemini-3.6-flash` warns that it uses fixed sampling defaults and
**ignores `temperature` entirely**, which would make Module 01's temperature
comparison meaningless on that model.

