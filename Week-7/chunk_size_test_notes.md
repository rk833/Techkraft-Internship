# Week 7 — Chunk Size Test Notes

Real output from running the chunking step (`chunk_documents.py`'s
logic) at three different chunk sizes against the same two sample
documents used throughout Weeks 6-7.

## Chunk counts by size

| Chunk size (words) | Overlap (words) | Total chunks (both docs) |
|---|---|---|
| 15 | 3 | 17 |
| 30 | 7 | 9 |
| 60 | 15 | 5 |

*(Verified by actually running the chunker — see terminal output
below.)*

```
chunk_size=15, overlap=3  -> total chunks: 17
chunk_size=30, overlap=7  -> total chunks: 9
chunk_size=60, overlap=15 -> total chunks: 5
```

## Observations

- **Chunk count scales inversely with chunk size**, as expected —
  going from 60-word to 15-word chunks roughly quadruples the chunk
  count (5 → 17, not exactly 4x because of how overlap and document
  boundaries interact, but the direction is consistent).
- **Smaller chunks (15 words) are closer to a single sentence or
  sentence fragment.** This means retrieval can be very precise (you
  get exactly the relevant sentence) but each chunk has very little
  surrounding context — if the LLM needs adjacent sentences to make
  sense of a chunk, a 15-word chunk might not give it enough.
- **Larger chunks (60 words) span 2-3 sentences worth of content.**
  This gives the LLM more context per chunk, but increases the risk
  that a chunk contains a mix of relevant and irrelevant material,
  which can dilute the embedding's similarity score for the part that
  actually answers the question.
- **The 30-word setting (used as the default in `retrieval.py`) is a
  middle ground** — roughly 1-2 sentences per chunk, which has worked
  reasonably well in practice for the two short sample documents used
  here.

## What I'd still want to test with a real embedding model

This chunk-count comparison is fully verified (real chunker code, real
counts). What I haven't been able to verify directly in this
environment is how chunk size affects **retrieval quality** —
specifically:
- Does the top-ranked chunk change as chunk size changes, for the same
  query?
- Do similarity scores get systematically lower for larger chunks
  (since they contain more "noise" alongside the relevant part)?

`test_chunk_sizes.py` is written to answer exactly this — it runs the
same query against indexes built at each chunk size and prints the
top match and its score. Once it's run for real (with the embedding
model downloaded), I'll add actual scores here for comparison.

## Practical takeaway for future RAG work (GhumGham)

For something like a Nepal travel Q&A use case, chunk size probably
shouldn't be one-size-fits-all:
- Permit requirements, prices, and other short factual snippets:
  smaller chunks, so retrieval pinpoints the exact fact
- Descriptive content (e.g. "what's it like to trek to X") benefits
  from slightly larger chunks so the LLM gets enough narrative context
  to generate a coherent answer, not just an isolated fact fragment
