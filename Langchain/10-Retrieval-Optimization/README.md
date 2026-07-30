# Module 10 - Retrieval Optimization

**Status:** complete. All four methods run, with a result that contradicts the
usual advice.

## Goal

Fix the retrieval failures found in Modules 07 and 09 by combining keyword and
semantic search, and find out whether reranking actually helps.

## Topics covered

| Topic | Method |
|-------|--------|
| BM25 | `--method keyword` |
| Semantic search | `--method semantic` |
| Hybrid search | `--method hybrid` |
| Cross encoder reranking | `--method reranked` |

## Files

| File | Purpose |
|------|---------|
| `search_comparison.py` | The mini project. Four methods, three commands. |
| `support_articles.txt` | Ten support articles, written so the methods disagree. |

## Setup

```powershell
pip install -r ..\requirements.txt
python search_comparison.py build
```

The cross encoder model is downloaded on first use, about 4 MB, and cached in
this folder.

## Running it

```powershell
python search_comparison.py compare --query "ERR_4021"
python search_comparison.py compare --query "our service gradually eats more RAM until we bounce it"
python search_comparison.py search --query "..." --method keyword
python search_comparison.py search --query "..." --method reranked --rerank-model ms-marco-MultiBERT-L-12
```

**Cost:** `build` is one batched embed call. `keyword` costs **nothing at all** -
no embeddings, no network. `compare` costs three embed calls, one for each
method that uses the vector store. The cross encoder runs locally.

## What you should see

### A paraphrase query, where keyword search fails

```powershell
python search_comparison.py compare --query "our service gradually eats more RAM until we bounce it"
```

```
rank  keyword     semantic    hybrid      reranked
------------------------------------------------------
1     kb-010      kb-008      kb-008      kb-008
2     kb-005      kb-002      kb-010      kb-002
3     kb-008      kb-003      kb-005      kb-007
4     kb-004      kb-007      kb-002      kb-005

  kb-008  Memory grows until the service is restarted   <- the right answer
  kb-010  Outbound email lands in the spam folder
```

**BM25 put the spam folder article first** and the correct one third. The query
says "RAM", "bounce" and "eats"; the article says "memory", "restarted" and
"climbs". No shared rare terms, so BM25 has nothing to work with.

Semantic search got it first. Hybrid kept it first. This is the case embeddings
exist for.

### An exact token query, where keyword search shines

```powershell
python search_comparison.py compare --query "ERR_4021"
```

```
rank  keyword     semantic    hybrid      reranked
------------------------------------------------------
1     kb-001      kb-001      kb-001      kb-001
2     kb-010      kb-005      kb-010      kb-005
3     kb-009      kb-003      kb-005      kb-010
```

Everything agrees at rank 1 here, but look at rank 2 for semantic: **kb-005 is
`ERR_5150`**, a completely different error. The embedding recognised the shape
of an error code without distinguishing which one. On a corpus with hundreds of
codes that is exactly how semantic search goes wrong, and why you want BM25 in
the mix.

## What each method does

### BM25 (keyword)

Scores on term overlap, weighting rare words heavily and penalising long
documents. It has no idea what any word means, which is both its weakness and
its strength: an error code, a product name or a version number is a rare token
it matches exactly, where an embedding blurs it into "things that look like
error codes".

Costs nothing and needs no index on disk. It is rebuilt from the text at query
time, because it indexes words rather than vectors.

### Hybrid, via EnsembleRetriever

Runs both and merges with **reciprocal rank fusion**: each document scores
`1/(rank + constant)` in every list it appears in, and those are summed.

The important detail is that fusion uses **ranks, not scores**. BM25 scores and
cosine distances are on completely unrelated scales, as Modules 06 and 07
established, so averaging the raw numbers would be meaningless. Ranks are
comparable, so ranks are what get combined.

In both queries above, hybrid matched whichever method was right. That is the
point: you do not have to guess which one suits a given query.

### Cross encoder reranking

A bi-encoder, which is what everything so far has used, embeds the query and the
document **separately** and compares the two vectors. A cross encoder reads the
query and document **together** and scores the pair directly. It sees the
interaction between them, so it is much more accurate in principle, and far too
slow to run over a whole corpus. It only reorders what retrieval already
shortlisted.

## The finding: reranking made results worse here

Standard advice is to bolt a reranker onto the end of any retrieval pipeline.
Tested on this corpus, it never helped and once did real damage.

```powershell
python search_comparison.py compare --query "after changing my credentials I keep getting kicked out"
```

```
rank  keyword     semantic    hybrid      reranked
------------------------------------------------------
1     kb-003      kb-004      kb-004      kb-007
2     kb-004      kb-001      kb-007      kb-001
3     kb-007      kb-010      kb-003      kb-002
4     kb-002      kb-007      kb-001      kb-004

  kb-004  Login loop after a password reset   <- the right answer
```

Semantic and hybrid both put the correct article **first**. The reranker moved
it to **last**, and promoted an article about scheduled report timezones.

That is not a tie, it is a regression. Checking whether it was model capacity,
the larger cross encoder was tried too:

| Reranker | Rank of the correct article |
|----------|----------------------------|
| none (hybrid) | **1** |
| `ms-marco-TinyBERT-L-2-v2` (4 MB) | 4 |
| `ms-marco-MultiBERT-L-12` (99 MB) | 4 |

Both failed. Across all three test queries, reranking improved rank 1 in **zero**
cases and worsened it in **one**.

### Why, and what to take from it

Likely causes, in order of confidence:

- **Domain mismatch.** These models are trained on MS MARCO, which is web search
  passages answering short factual queries. A conversational first-person
  complaint like "I keep getting kicked out" is not that shape.
- **The corpus is tiny.** Reranking earns its keep by sorting 50 to 100
  candidates down to 5. Reordering 4 already-good results has little upside and
  plenty of downside.
- **Nothing was calibrated.** A reranker is a model with its own training
  distribution. Dropping one in unmeasured is the same mistake as copying a
  similarity threshold from a tutorial, which Module 06 covered.

**The lesson is not "rerankers are bad".** They genuinely help on large corpora
in the domain they were trained for. The lesson is that this is an empirical
question about your data, and this module is the tool for answering it. Run
`compare` on ten questions you know the answers to before adding a reranker to
anything real.

That is also why `--rerank-model` exists: swapping the model is one flag, so the
comparison is cheap to redo.

## Choosing a method

| Situation | Use |
|-----------|-----|
| identifiers, codes, names, versions | keyword, or hybrid |
| users describe problems in their own words | semantic, or hybrid |
| you do not know which, which is usual | **hybrid** |
| large corpus, in-domain reranker, measured | add reranking |
| small corpus, general purpose reranker | measure first, expect nothing |

Hybrid is the safe default. It costs the same as semantic search, since BM25 is
free, and it protects against both failure modes.

## Things worth knowing

### FlashRank instead of sentence-transformers

The original plan named a `sentence-transformers` cross encoder. That pulls in
PyTorch, roughly 2 GB. `flashrank` runs the same class of model on
`onnxruntime`, which `chromadb` already installs, so the package added **0.1 MB**
and the model is 4 MB.

Both are genuine cross encoders, so nothing is lost pedagogically.

Watch the default though: `FlashrankRerank()` with no arguments downloads
`ms-marco-MultiBERT-L-12`, about **99 MB**. The model is named explicitly here so
that is a choice rather than a surprise.

### The corpus was built to make the methods disagree

Articles contain deliberate rare tokens (`ERR_4021`, `ERR_5150`) that favour
BM25, and describe problems in vocabulary users would not use, which favours
embeddings.

An earlier attempt failed because the article about slow cold starts literally
contained the words "hanging" and "taking ages", so BM25 found it easily and
every method agreed. **Writing an evaluation set is harder than it looks**, and
a set where everything agrees teaches nothing.

### Reciprocal rank fusion needs no tuning

`weights=[0.5, 0.5]` gives BM25 and semantic equal say. Because fusion works on
ranks, those weights are the only knob, and there is no scale mismatch to
correct. Compare with the `EmbeddingsFilter` threshold in Module 09, which is a
raw similarity value and has to be recalibrated whenever the embedding model
changes.


