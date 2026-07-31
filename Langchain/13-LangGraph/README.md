# Module 13 - LangGraph

**Status:** complete. Runs against the live API, including the revision loop and
the safety cap.

## Goal

Build a workflow that can decide where to go next, and can send work back to a
step that has already run.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| Nodes | `research`, `summarize`, `review`, `finalize` |
| Edges | `add_edge` |
| State | `ResearchState` |
| Conditional routing | `add_conditional_edges`, `route_after_review` |

## Files

| File | Purpose |
|------|---------|
| `research_workflow.py` | The mini project. Four nodes, one loop. |

## Running it

```powershell
python research_workflow.py show
python research_workflow.py run --question "What was Charles Babbage's Analytical Engine?"
python research_workflow.py run --question "..." --force-revisions 1
python research_workflow.py run --question "..." --force-revisions 9 --max-revisions 2
python research_workflow.py run --question "..." --strict
```

| Command | Cost |
|---------|------|
| `show` | none, compiling a graph does not run it |
| `run` | 2 calls minimum, plus 2 per revision |

`research` uses Wikipedia rather than a model, and `finalize` is pure Python, so
neither costs anything. Only `summarize` and `review` call the model.

## The shape of the workflow

```
question -> research -> summarize -> review -> final answer
                             ^          |
                             +--revise--+
```

## What you should see

### show

```
edges:
  __start__  --> research
  research   --> summarize
  review     ..> finalize
  review     ..> summarize
  summarize  --> review
  finalize   --> __end__
```

`-->` is a fixed edge, `..>` is conditional. **`review ..> summarize` is the
whole module.** It points backwards, to a node that has already run, and a chain
cannot express that. Module 04's chain was a straight line by construction.

The ascii diagram above the edge list draws nodes top to bottom and does not make
the back edge obvious, which is why the edges are listed separately.

### run, approved first time

```
[research]  gathered 501 characters of source material
[summarize] wrote 61 words
[review]    approved (attempt 1)
[finalize]  assembled the answer, no model call

final answer:
The Analytical Engine was a proposed digital mechanical general-purpose
computer designed by ... Charles Babbage. First described in 1837, ...
```

Two model calls. The loop existed but was not needed.

### run, with the loop firing

```powershell
python research_workflow.py run --question "..." --force-revisions 1
```

```
[summarize] wrote 62 words
[review]    rejected (attempt 1)
            feedback: Forced revision for demonstration. Make the answer more
                      specific and mention the date it was first described.
[summarize] wrote 62 words
[review]    approved (attempt 2)
[finalize]  assembled the answer, no model call
```

`summarize` ran **twice**, because `review` sent it back. The state carried the
feedback with it, so the second attempt was a rewrite rather than a repeat.

### run, hitting the safety cap

```powershell
python research_workflow.py run --question "..." --force-revisions 9 --max-revisions 2
```

```
[review]    rejected (attempt 1)
[review]    rejected (attempt 2)
[finalize]  assembled the answer, no model call

final answer:
... (returned unapproved, revision limit reached)
```

The reviewer would have rejected forever. `max_revisions` stopped it after two
and passed the summary through with a flag saying so.

## Why --force-revisions exists

An honest note. On this question the model wrote a good summary first time, and
the reviewer approved it, in both normal and `--strict` mode. So the most
interesting edge in the graph never fired, and an untested loop is an unverified
loop.

`--force-revisions N` rejects the first N attempts outright. It is a demo aid,
clearly labelled as one in the code, and it costs nothing because it returns a
canned rejection without calling a model.

It is also the honest way to test a cycle. Waiting for a model to fail naturally
is not a test, it is hoping.

## How a graph differs from a chain

Module 04 built `prompt | model | parser`. Everything ran once, in order,
forwards. That covers most work.

A graph is worth the extra machinery when:

- **a step decides what happens next**, rather than the code deciding in advance
- **work goes backwards**, as with review and revise
- **the number of steps is not known** until it runs

The cost is that state has to be explicit and cycles have to be bounded.

## The pieces

### State is one dictionary

```python
class ResearchState(TypedDict):
    question: str
    research: str
    summary: str
    approved: bool
    feedback: str
    revisions: int
    ...
```

Every node receives the whole state and returns **only the keys it changed**.
LangGraph merges the update in. That is why `summarize` can read `feedback`
written by `review` without either function knowing the other exists.

### Nodes are ordinary functions

```python
def finalize(state: ResearchState) -> dict:
    note = "" if state["approved"] else " (returned unapproved, ...)"
    return {"answer": state["summary"] + note}
```

No base class, no decorator. `research` makes HTTP calls, `finalize` is pure
string handling, and neither touches a model. **The graph coordinates steps
without caring what they do**, which is the same point Module 04 made about
`RunnableLambda`.

### The conditional edge is the interesting part

```python
def route_after_review(state: ResearchState) -> str:
    if state["approved"]:
        return "finalize"
    if state["revisions"] >= state["max_revisions"]:
        return "finalize"
    return "summarize"
```

It returns the **name of the next node**. Everything about the shape of the run
is decided here, at runtime, from the state.

### Routing needs structured output, not prose

`review` uses `with_structured_output(Review)` from Module 01:

```python
class Review(BaseModel):
    approved: bool
    feedback: str
```

`route_after_review` branches on `state["approved"]`, a real boolean. If the
reviewer returned prose, the router would have to search it for the word
"approved", and a routing decision made by string matching is a routing decision
that eventually breaks. **Structured output is what makes routing safe.**

### Feedback is what makes looping useful

Sending work back only helps if something changed. `summarize` adds the
reviewer's feedback and the rejected attempt to its prompt on a revision:

```python
if state.get("feedback"):
    instruction += f"A previous attempt was rejected for this reason:\n{state['feedback']}..."
```

Without that, the second pass would produce the same output as the first and the
graph would cycle until the cap stopped it, burning two calls per lap for
nothing.

## Cycles need a cap

`max_revisions` is not a nicety. A graph with a cycle and no exit condition is an
infinite loop with extra steps, and here each lap costs two API calls.

Two things guard it:

- the router checks `revisions >= max_revisions`
- the counter increments in `review`, which is on the cycle, so it always
  advances

If the counter were incremented somewhere off the cycle, the cap would never
trigger. Worth checking whenever you add a loop.

## You have already used this

`create_agent` in Module 11 builds a LangGraph graph. Its loop is:

```
call model -> did it ask for tools? -> yes: run them, go back
                                    -> no:  finish
```

That is a conditional edge and a cycle, exactly like this module's, with the
router looking at tool calls instead of an approval flag. Module 11 worked
without you seeing the graph; this module shows what was underneath.

