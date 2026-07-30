# Module 08 - Basic RAG

**Status:** complete. All three commands run against the live API.

## Goal

Assemble the pieces from Modules 05 to 07 into a working
Retrieval-Augmented Generation pipeline, and find out what the prompt actually
contributes.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| Retriever | `store.as_retriever(...)` |
| Context | `format_context` |
| Prompt plus retrieval | `build_chain`, `GROUNDED_PROMPT` |
| Citations | page numbers injected into the context |

## Files

| File | Purpose |
|------|---------|
| `rag_chat.py` | The mini project. Three commands. |
| `make_sample.py` | Writes `handbook.pdf`, the document being queried. |

`handbook.pdf` is a four page staff handbook with specific, checkable facts.
Some obvious questions are deliberately **not** answerable from it: nothing
about parental leave, resignation notice, salary or pensions. That is what makes
the refusal behaviour testable.

## Setup

```powershell
python make_sample.py
python rag_chat.py build
```

## Running it

```powershell
python rag_chat.py show --question "how many days of annual leave do I get"
python rag_chat.py ask  --question "how many days of annual leave do I get"
python rag_chat.py ask  --question "..." --show-context
python rag_chat.py ask  --question "..." --no-grounding
```

| Command | Cost |
|---------|------|
| `build` | 1 call, every chunk embedded in one batch |
| `show` | 1 call, embeds the question only, no chat model |
| `ask` | 2 calls, one to embed the question, one to answer |

**Use `show` while exploring.** If the right chunk is not retrieved, no prompt
will save the answer, and `show` diagnoses that for half the cost.

## How the pipeline fits together

```
handbook.pdf
  -> PyPDFLoader                 one Document per page      (Module 05)
  -> RecursiveCharacterTextSplitter   7 chunks              (Module 05)
  -> embed in one batch                                     (Module 06)
  -> Chroma, persisted to disk                              (Module 07)

question
  -> embed
  -> retrieve k nearest chunks
  -> format into a context block with page numbers
  -> prompt + model + parser                                (Module 04)
```

The chain is ordinary LCEL. A retriever is just another runnable:

```python
RunnablePassthrough.assign(
    context=(lambda inputs: inputs["question"]) | retriever | RunnableLambda(format_context)
)
| prompt
| model
| StrOutputParser()
```

`.assign` runs retrieval and adds the result under `context`, while keeping
`question` for the prompt, exactly as in Module 04.

## What you should see

### show

```
question: how many days of annual leave do I get and can I carry them over
retrieved 3 chunks

[0] page 1
    Northbridge Analytics - Staff Handbook Section 1: Annual Leave Full time
    staff receive 25 days of annual leave per year... Up to 5 unused days may
    be carried into the following year...

[1] page 1
    and must be approved by a line manager before travel is booked...

[2] page 3
    Section 3: Remote Work Staff may work remotely up to 3 days per week...
```

Chunk 0 holds the answer. Chunks 1 and 2 are filler, and chunk 2 is about
remote work, which is unrelated. **That is normal.** The retriever returns k
chunks regardless, exactly as Module 07 found.

### ask

```
question: how many days of annual leave do I get and can I carry them over

Full time staff receive 25 days of annual leave per year (page 1). Up to 5
unused days may be carried into the following year (page 1).
```

Both numbers correct, both cited, and the irrelevant remote work chunk ignored.

### ask, with no answer in the document

```powershell
python rag_chat.py ask --question "what is the parental leave policy and how much is paid"
```

```
I don't know based on the handbook.
```

The exact sentinel string from the prompt. This matters more than it looks -
see below.

## The finding: grounding did not prevent hallucination here

Most RAG tutorials claim that without an instruction like "use only the
context", the model will invent answers. That was tested here, four times, and
**it did not happen once**.

With the grounding instructions removed via `--no-grounding`:

| Question | Answerable? | Ungrounded response |
|----------|-------------|---------------------|
| parental leave policy and pay | no | "there is no information regarding a parental leave policy" |
| resignation notice, pension rate | no | "there is no information regarding resignation notice periods or pension contribution rates" |
| when can I claim a taxi | yes | correct: 22:00 to 06:00, or equipment over 10kg |

`gemini-3.1-flash-lite` refused honestly every time, unprompted. Repeating a
2023-era warning about hallucination would be teaching something that is no
longer reliably true of current models on this kind of question.

**So what did the grounding instructions actually buy?** Two things, both
consistent across every test:

**Citations.** The grounded answers cite `(page 1)`, `(page 2)`. The ungrounded
answers never cite anything. Nothing in the ungrounded prompt asked for it, and
the model did not volunteer it.

**A fixed refusal string.** Grounded refusals are always exactly
`I don't know based on the handbook.` Ungrounded refusals are free prose that
varies every run: "there is no information regarding...", "the handbook
currently only covers...". A fixed string can be **detected in code**:

```python
if answer.strip() == "I don't know based on the handbook.":
    ...fall back to search, or escalate to a human
```

You cannot do that reliably against prose that changes wording each time. In a
real system this is the difference between a pipeline that can route a failed
answer somewhere useful and one that cannot.

The ungrounded version also drifted into markdown bullets and bold text, which
the grounded one did not.

### Why keep the instruction anyway

- **It converts luck into a contract.** The model behaved well; it was not
  required to. On an ambiguous question, or with partially relevant context,
  the pressure to answer is much higher than on a clean "not in the document"
  case.
- **It is model dependent.** Smaller, older, or locally hosted models are far
  less well behaved. The instruction costs a few tokens.
- **It makes failure machine readable**, as above.

The honest summary: grounding instructions are cheap insurance and a formatting
contract, not a magic hallucination switch. Test your own model rather than
trusting either claim.

## Things worth knowing

### The model cannot see metadata

Chunks carry `page_label` in metadata, but metadata is not sent to the model.
Only `page_content` is. So `format_context` writes the page number **into the
text**:

```python
blocks.append(f"[page {page}]\n{document.page_content}")
```

Without this, asking for citations invites invented page numbers, because the
model would have no way of knowing the real ones. **If you want the model to
use a fact, put it in the string.**

### Retrieval quality caps everything

The prompt cannot recover from a bad retrieve. If the chunk holding the answer
is not in the top k, the model's options are to refuse or to make something up,
and neither is the answer you wanted.

This is why `show` exists, and why Modules 09 and 10 are about retrieval rather
than prompting. When a RAG answer is wrong, **check what was retrieved before
touching the prompt.**

### Chunk size interacts with citations

At `--chunk-size 600` the handbook produces 7 chunks and most chunks sit inside
one page, so page citations are clean. Larger chunks can span a page boundary,
and the chunk then carries the metadata of the page it started on, so a citation
can point at the wrong page. Worth knowing before trusting citations in a real
system.

### temperature 0.0

Extraction, not writing. The same question against the same document should
give the same answer. This follows Module 03 rather than Module 04.

