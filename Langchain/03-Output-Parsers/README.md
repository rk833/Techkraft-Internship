# Module 03 - Output Parsers

**Status:** complete. All three modes run against the live API.

## Goal

Turn a model's free text reply into data your program can use, and understand
where the formatting instructions come from.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| StrOutputParser | `--mode str` |
| JsonOutputParser | `--mode json` |
| PydanticOutputParser | `--mode pydantic` |
| Format instructions from a schema | `--show-prompt` |

## Files

| File | Purpose |
|------|---------|
| `review_analyzer.py` | The mini project. Three parsers, same task. |
| `sample_review.txt` | A deliberately mixed review, so the output is not all praise. |

## Running it

```powershell
python review_analyzer.py --file sample_review.txt --mode pydantic
python review_analyzer.py --file sample_review.txt --mode json
python review_analyzer.py --file sample_review.txt --mode str
python review_analyzer.py --file sample_review.txt --mode pydantic --show-prompt
python review_analyzer.py --review "your own review text" --mode pydantic
```

| Flag | Meaning |
|------|---------|
| `--file` | path to a review file (default `sample_review.txt`) |
| `--review` | review text given directly instead of a file |
| `--mode` | `str`, `json` or `pydantic` (default `pydantic`) |
| `--show-prompt` | print the rendered prompt including generated format instructions |
| `--debug` | show the full traceback |

## What you should see

### pydantic

```
parsed type: ReviewAnalysis

sentiment:  Positive
rating:     7
themes:     emotional storytelling, character performance
praise:     moving story; strong lead performance
criticism:  slow first half hour; pointless subplot; intrusive score; rushed ending
summary:    Despite pacing issues and a loud score, the film is a moving experience anchored by a great lead performance.
```

The rating should land around 6 to 8 and sentiment should be `Positive` or
`Mixed`, because the sample review is genuinely mixed. Wording will vary between
runs, but the criticisms should map to things actually in the review: the slow
opening, the brother subplot, the loud score, the rushed ending. If it reports
something not in the review, that is worth noticing.

### json

Same information, printed as JSON, with `parsed type: dict`.

### str

```
parsed type: TextAccessor

Sentiment: Positive
Rating: 7/10
Main themes: Emotional journey, family dynamics.
What the reviewer praised: ...
What the reviewer criticised: ...
```

Prose, not data. The layout will drift between runs because nothing enforces it.

## The three parsers compared

| Parser | Returns | Schema | Validation |
|--------|---------|--------|------------|
| `StrOutputParser` | the reply text | none | none |
| `JsonOutputParser` | `dict` | optional | shape only, no types |
| `PydanticOutputParser` | your class | required | full, typed |

### StrOutputParser

Pulls the text out of the `AIMessage`. That is all it does. There is no schema,
so the prompt has to describe the wanted output in prose, and nothing checks the
result. Fine when the output is meant to be read by a person.

Note the reported type is `TextAccessor`, not `str`. That is a LangChain 1.x
detail: it behaves like a string, so `.strip()` and printing work normally, but
`isinstance(result, str)` is `False`. Wrap it in `str()` if you need a real one.

### JsonOutputParser

Returns a plain `dict`. Given a `pydantic_object` it generates format
instructions from that schema, but **it does not validate against it**. A
missing key or a rating of `"seven"` instead of `7` passes straight through and
fails later, somewhere else in your code.

### PydanticOutputParser

Returns an instance of your class, validated. A wrong type or missing field
raises `OutputParserException` immediately, at the boundary, where the error is
still easy to understand.

**Use this one by default.** The failure happens in the right place.

## Where format instructions come from

This is the real lesson of the module. Run:

```powershell
python review_analyzer.py --show-prompt --mode pydantic
```

and look at the system message. Neither parser was told what a review analysis
looks like. Both generated this from the `ReviewAnalysis` class:

```
The output should be formatted as a JSON instance that conforms to the JSON
schema below.
...
{"properties": {"sentiment": {"description": "one of: Positive, Negative, Mixed",
"type": "string"}, "rating": {"description": "overall rating from 1 to 10", ...
```

Two consequences that are easy to miss:

**Every `Field(description=...)` is sent to the model on every call.** They are
instructions, not code comments. Vague descriptions produce vague output, and
long ones cost input tokens each time.

**The class docstring is sent too.** The first version of this file had a
docstring explaining the teaching point of the class, and all of it went into
the prompt. It is now one short line, with the commentary moved to a `#` comment
above the class, which is not part of the schema.

The prompt uses `.partial(format_instructions=...)` to fill that slot once at
build time, since the instructions come from the schema rather than from user
input.

## Parsers versus with_structured_output

Module 01 got typed output with `model.with_structured_output(Joke)`. This
module gets it with a parser. They are not the same mechanism.

| | `with_structured_output` | `PydanticOutputParser` |
|---|---|---|
| How | provider's native structured output | instructions in the prompt, then parse |
| Reliability | higher, the provider enforces it | depends on the model following instructions |
| Portability | only models that support it | any model that emits text |
| Visibility | schema handling is hidden | you can see the instructions in the prompt |
| Token cost | lower | schema is in every prompt |

Prefer `with_structured_output` when the model supports it. Parsers are the
fallback, and are what you need for local or smaller models.

## Temperature 0.0

This module uses `temperature=0.0`, unlike Modules 01 and 02. Extraction should
be repeatable: the same review should produce the same analysis. Creative
variation is a bug here, not a feature.

## Handling parse failures

When the model returns something unparseable, the script prints the raw reply
alongside the parser error rather than a traceback. Seeing what the model
actually said is usually what tells you whether the prompt or the schema is at
fault.

To provoke it, shrink `max_output_tokens` so the JSON gets truncated, and the
parser will fail on incomplete input.

