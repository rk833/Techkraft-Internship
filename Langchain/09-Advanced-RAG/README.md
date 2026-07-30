# Module 09 - Advanced RAG

**Status:** complete. All five retrievers run against the live API.

## Goal

Improve the retrieval half of RAG, since Module 08 showed that a bad retrieve
cannot be rescued by a better prompt.

## Topics covered

| Topic | Retriever |
|-------|-----------|
| MultiQueryRetriever | `--retriever multiquery` |
| ParentDocumentRetriever | `--retriever parent` |
| Context compression | `--retriever compression` |
| SelfQueryRetriever | `--retriever selfquery` |
| Multi-document search | all of them |

## Files

| File | Purpose |
|------|---------|
| `research_assistant.py` | The mini project. Five retrievers, four commands. |
| `make_samples.py` | Writes the three PDFs. |

Three documents, each owned by a different department:

| Document | Department | Year |
|----------|-----------|------|
| `people-handbook.pdf` | people | 2025 |
| `security-policy.pdf` | security | 2026 |
| `engineering-guide.pdf` | engineering | 2026 |

They are written to **overlap and partly disagree**. Both the handbook and the
security policy cover a stolen laptop, from different angles, which is what
makes cross-document retrieval worth testing.

## Setup

```powershell
python make_samples.py
python research_assistant.py build
```

## Running it

```powershell
python research_assistant.py show --question "..." --retriever basic
python research_assistant.py compare --question "..." --retrievers basic,multiquery,compression
python research_assistant.py ask --question "..." --retriever multiquery
```

| Command | What it does |
|---------|--------------|
| `build` | index the PDFs, one batched embed call |
| `show` | retrieve and print, **no chat model** |
| `compare` | several retrievers on one question, retrieval only |
| `ask` | retrieve and answer |

## Cost, which is the thing to watch here

This is the most expensive module in the course. Approximate calls per question:

| Retriever | Chat calls | Embed calls | Notes |
|-----------|-----------|-------------|-------|
| `basic` | 0 | 1 | the Module 08 baseline |
| `parent` | 0 | 1 + a full re-index | in-memory parent store, rebuilt each run |
| `compression` | 0 | 2 | filter embeds the query and the candidates |
| `selfquery` | 1 | 1 | one call to parse the question |
| `multiquery` | 1 | 3 to 4 | one call to rewrite, one search per rewrite |

Add one more chat call if you use `ask` instead of `show`.

**Use `show` and `compare` while learning.** They exercise the retriever without
generating an answer, which is where the interesting differences are anyway.

## What you should see

### compare

```powershell
python research_assistant.py compare --question "my laptop was stolen, what do I do" --retrievers basic,multiquery,compression
```

```
--- basic ---
  4 chunks, 2 document(s), avg 384 chars
    people-handbook.pdf: 1
    security-policy.pdf: 3

--- multiquery ---
  5 chunks, 3 document(s), avg 403 chars
    engineering-guide.pdf: 1
    people-handbook.pdf: 1
    security-policy.pdf: 3

--- compression ---
  2 chunks, 2 document(s), avg 463 chars
    people-handbook.pdf: 1
    security-policy.pdf: 1
```

This one output is most of the module:

- **`multiquery` widened the net.** Five chunks across all three documents. It
  found more, including a chunk from the engineering guide that is arguably
  noise. Higher recall, lower precision.
- **`compression` narrowed it.** Two chunks, and they are the two that actually
  answer the question. Higher precision, and a risk of dropping something
  needed.
- **`basic` sits in between**, which is what a baseline should do.

Neither is simply better. They move in opposite directions, and which one you
want depends on whether your failure mode is missing information or drowning in
it.

### selfquery

```powershell
python research_assistant.py show --question "what do the engineering docs say about deploying on a Friday" --retriever selfquery --top 3
```

```
retrieved: 2 chunks
  [0] engineering-guide.pdf page 1
      ... Deployments to production run Monday to Thursday only. Friday deploys
      need written approval from the on call engineer and a director...
  [1] engineering-guide.pdf page 2
documents covered: engineering-guide.pdf
```

Two things worth noticing.

**Only the engineering guide came back.** An LLM read the question, worked out
that "the engineering docs" means `department = engineering`, and turned that
into a metadata filter. The vector search then ran over engineering chunks only.

**It returned 2 chunks for `--top 3`.** After filtering there were only two
candidates left. Unlike plain similarity search, which always returns k, a
filtered search can return fewer. That is usually what you want.

### ask, on a genuinely cross-document question

```powershell
python research_assistant.py ask --question "my laptop was stolen, who do I contact and in what order" --retriever multiquery
```

```
You must report the stolen laptop to the security team immediately, and in all
cases within 24 hours (security-policy.pdf page 2; people-handbook.pdf page 2).

*   Security Team: report the theft first. They will remotely wipe the device
    and revoke its certificates (security-policy.pdf page 2).
*   People Team: do not contact them for a replacement until the wipe has been
    confirmed (security-policy.pdf page 2).
*   Discrepancy: while both documents agree on the 24 hour deadline, the
    people-handbook.pdf adds that a police reference number is required for the
    insurance claim, which is not mentioned in security-policy.pdf.
```

The ordering is correct, both documents are cited, and the model flagged that
one document contains a requirement the other omits. That last part comes from
one line in the prompt: *"When two documents disagree or overlap, say so
explicitly."* Worth keeping in any multi-source RAG prompt.

## How each retriever works

### MultiQueryRetriever

One LLM call rewrites the question several ways, each rewrite is searched, and
the results are merged and deduplicated.

The point is that a question and the passage answering it may share no
vocabulary. "My laptop was stolen" and "lost device reporting procedure" mean
the same thing to a person and sit some distance apart in embedding space.
Rewriting gives several shots at closing that gap.

Cost: one chat call plus one search per rewrite, so about four calls where
basic uses one. Use it when recall matters more than budget.

### ParentDocumentRetriever

Indexes **small** chunks but returns the **larger** section containing them.

This resolves the tension from Module 05: small chunks match precisely but lack
context, large chunks carry context but match weakly. Here the child chunks are
200 characters and the parents 900.

Its cost is hidden. The parent store in this module is `InMemoryStore`, so it is
rebuilt and re-embedded on every single run. That is fine for a demo and wrong
for anything real, where the parent store would be persisted alongside the
vectors.

### ContextualCompressionRetriever

Retrieves widely, then discards what does not clear a bar. Here it fetches
`top * 2` and filters with `EmbeddingsFilter` at a similarity threshold of 0.55.

**`EmbeddingsFilter` was chosen deliberately.** The alternative,
`LLMChainExtractor`, asks a model to pull the relevant sentences out of every
retrieved chunk, which means **one LLM call per chunk**. It produces tighter
context and it would exhaust a day's free quota in three questions.

Note the threshold is a magic number, and Module 06 explained why that is
dangerous: absolute similarity scores are not comparable across models or task
types. 0.55 was picked against this corpus and this embedding model. Change
either and it needs recalibrating.

### SelfQueryRetriever

One LLM call splits a question into a search string and a metadata filter,
using the field descriptions in `METADATA_FIELDS`:

```python
AttributeInfo(
    name="department",
    description="Which team owns the document. One of: people, security, engineering.",
    type="string",
)
```

Those descriptions are read by the model, exactly like the `Field` descriptions
in Module 03. Listing the allowed values is what lets it map "the engineering
docs" onto `department = engineering`.

Best when your corpus has real structure and questions refer to it. Useless if
everything sits in one undifferentiated pile.

## Things that caused real problems

### langchain.retrievers no longer exists

Every one of these retrievers used to live in `langchain.retrievers`. In
LangChain 1.x the `langchain` package contains only:

```
agents, chat_models, embeddings, messages, rate_limiters, tools
```

The retrievers moved to **`langchain_classic`**, which ships with LangChain and
does not need installing separately:

```python
from langchain_classic.retrievers import ParentDocumentRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
```

Any tutorial doing `from langchain.retrievers import ...` fails immediately on
1.x. This is the largest single break between versions encountered so far.

### AttributeInfo moved too

Not to `langchain_core.structured_query`, which is a plausible guess and holds
the filter expression types instead. It is at:

```python
from langchain_classic.chains.query_constructor.schema import AttributeInfo
```

### SelfQueryRetriever.from_llm crashes on auto-detection

The obvious call fails:

```
cannot import name 'DatabricksVectorSearch' from 'langchain_community.vectorstores'
```

Left to itself, `from_llm` inspects the vector store to choose a query
translator, and that lookup imports every supported vector store. One of them
does not exist in this combination of `langchain-classic` and
`langchain-community` versions, so the whole thing fails, with an error naming a
product you are not using.

The fix is to pass the translator explicitly and skip the detection:

```python
from langchain_community.query_constructors.chroma import ChromaTranslator

SelfQueryRetriever.from_llm(..., structured_query_translator=ChromaTranslator())
```

Worth remembering as a pattern: an import error naming an unrelated integration
usually means something is auto-detecting by importing everything.

## Choosing between them

| Problem | Try |
|---------|-----|
| the right chunk is never retrieved | `multiquery` |
| retrieved chunks are right but too fragmentary | `parent` |
| too much irrelevant context reaches the model | `compression` |
| questions name a source, date or category | `selfquery` |
| none of the above | `basic`, and do not pay for more |

They compose, too. A production system might use `selfquery` to filter, then
compression to prune, at the cost of two LLM calls per question before an answer
is even generated.

