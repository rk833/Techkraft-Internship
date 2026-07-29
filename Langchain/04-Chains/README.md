# Module 04 - Chains

**Status:** complete. Both modes run against the live API.

## Goal

Compose several steps into one pipeline, where each step feeds the next.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| LCEL, the `\|` operator | `build_chain` |
| RunnableSequence | what `\|` produces |
| RunnableLambda | `clean_title`, `count_words` |
| RunnablePassthrough.assign | carrying values between steps |

## Files

| File | Purpose |
|------|---------|
| `story_generator.py` | The mini project. Topic to title to story to summary. |

## Running it

```powershell
python story_generator.py --show-graph --dry-run
python story_generator.py "a lighthouse keeper who is afraid of the dark"
python story_generator.py "..." --paragraphs 2
python story_generator.py "..." --mode manual
```

| Flag | Meaning |
|------|---------|
| `--mode` | `chain` (LCEL) or `manual` (written out by hand). Default `chain`. |
| `--paragraphs` | story length, default 3 |
| `--show-graph` | print the chain structure |
| `--dry-run` | build the chain, make no API calls |
| `--debug` | show the full traceback |

**Each run costs three API calls**, one per model step. `--dry-run` costs
nothing, so start there.

## What you should see

Start with the free one:

```powershell
python story_generator.py --show-graph --dry-run
```

An ASCII diagram of the pipeline. Three near-identical blocks, each
`ChatPromptTemplate -> ChatGoogleGenerativeAI -> StrOutputParser`, each wrapped
in a `Parallel<name>` pair, then a final `Parallel<word_count>` with no model in
it. No API calls are made, because building a chain does not run it.

Then a real run:

```
title: The Reverse Mainspring

Elara spent her life perfecting the rhythm of escapements, but the grandfather
clock in the corner of her workshop defied every law of horology she held dear.
[... two or three paragraphs ...]

summary: After discovering a clock that reverses time, a master horologist
experiences the world unspooling before the device erases her investigation.
words:   186
```

What to check:

- **The title has no quotes and no trailing full stop.** That is `clean_title`
  working. Models tend to return `"The Reverse Mainspring".` despite being told
  not to.
- **The story actually uses the title.** It is passed into the story prompt, so
  the two should agree. If the story ignores it, the chain is not wiring values
  through correctly.
- **The summary describes this story**, not the original topic. It only ever
  sees the generated story.
- **`words` roughly matches** the paragraph count you asked for.

The story itself differs every run, since temperature is 0.8.

## What the chain looks like

```python
title_chain = TITLE_PROMPT | model | parser | RunnableLambda(clean_title)
story_chain = STORY_PROMPT | model | parser
summary_chain = SUMMARY_PROMPT | model | parser

return (
    RunnablePassthrough.assign(title=title_chain)
    | RunnablePassthrough.assign(story=story_chain)
    | RunnablePassthrough.assign(summary=summary_chain)
    | RunnablePassthrough.assign(word_count=RunnableLambda(count_words))
)
```

### The pipe operator

`|` joins runnables into a `RunnableSequence`. Anything implementing the
runnable interface can take part: prompts, models, parsers, and plain functions
wrapped in `RunnableLambda`. That shared interface is the whole idea behind
LCEL, and it is why `prompt | model | parser` reads the same everywhere.

### Why RunnablePassthrough.assign

A chain passes one value from step to step. That is a problem here, because the
story step needs **both** the topic and the title.

`.assign(title=title_chain)` runs `title_chain` on the current dictionary and
adds the result under `title`, keeping everything already there. So the value
flowing through grows:

```
{topic}
{topic, title}
{topic, title, story}
{topic, title, story, summary}
{topic, title, story, summary, word_count}
```

This is why the graph shows `Parallel<title>` rather than a plain sequence: the
original dictionary and the new key travel side by side and are merged.

### RunnableLambda

`RunnableLambda` turns an ordinary Python function into a chain step. Two are
used here, for two different reasons:

- `clean_title` **repairs model output** before a later step depends on it.
  Cleaning once, at the point the value is produced, is much better than having
  every downstream step defend against quotes.
- `count_words` **adds a derived value with no model call**. It shows that not
  every link in a chain has to cost a request.

## Compare with --mode manual

`--mode manual` does the same three calls by hand. Read the two functions side
by side. The work is identical, so the comparison is about what LCEL actually
buys you:

**What it gives:** the plumbing disappears. No temporary variables, no
remembering to parse each response, and the structure becomes inspectable, which
is what makes `--show-graph`, streaming and async work for free.

**What it costs:** the flow is harder to read if you do not already know LCEL,
and stepping through it in a debugger is much less pleasant than stepping
through the manual version.

For a three step pipeline it is close to a tie. LCEL pays off as chains grow and
when you want streaming or parallel branches without rewriting anything.

## Things worth knowing

### Chains multiply cost

Three steps means three requests and three sets of tokens. Against a 20 per day
free quota, that is under seven runs on one model. The fallback chain in
`common/` covers this by rotating models, but chain length is worth thinking
about before adding a step.

### One model, one temperature

All three steps share one model instance at `temperature=0.8`. That suits the
story, but summarising would be better at `0.0`, since it is extraction rather
than writing.

Doing that properly means constructing a second model for the summary step, as
temperature is a constructor argument rather than something passed per call. It
was left as one model here to keep the chain readable, but it is a real
compromise, not a recommendation.

### Windows console encoding

The first run of this module printed `The Keeper?s Vigil`. The model had
returned a curly apostrophe, and the Windows console defaults to cp1252, which
cannot encode it.

`common/__init__.py` now switches stdout and stderr to UTF-8, which fixes it for
every module. Worth remembering whenever model output looks corrupted on
Windows: it is usually the terminal, not the model.

### Stripping quotes is not as simple as it looks

The first `clean_title` was a chain of `.strip()` calls. It failed on two real
cases:

| Input | Naive result | Why |
|-------|--------------|-----|
| `"Title".` | `Title"` | the full stop sits outside the quote and protects it |
| `"Nested 'Quotes'"` | `Nested 'Quotes` | both ends stripped independently, eating a real apostrophe |

The fix loops until the value stops changing, and only removes quotes when
**both** ends have one. Both cases are covered by the examples in the docstring.
