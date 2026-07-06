# Week 6: Embeddings and Vector Search

## Practice
- Split sample documents into chunks
- Create embeddings for text
- Search similar chunks

## Deliverable
- Mini document search demo

## Overview
This week builds the first two stages of a RAG pipeline: turning raw
text into chunks, and turning chunks into searchable vectors. Unlike
Week 5, this doesn't need a API key embeddings are generated
**locally** using a small open-source model (`all-MiniLM-L6-v2` via
`sentence-transformers`), so everything here is fully runnable.

## Files
| File | Type | Covers |
|---|---|---|
| `chunk_documents.py` | Practice | Split sample documents into chunks |
| `document_search_demo.py` | Practice + **Deliverable** | Create embeddings, search similar chunks, full demo |
| `chunk_output_sample.txt` | Reference | Real output from running the chunker |
| `requirements.txt` | Shared | Dependencies |

`document_search_demo.py` imports `chunk_documents.py`, so the chunking
practice and the search deliverable are connected, not duplicated.

---

## Setup

```bash
pip install -r requirements.txt
```

First run of the demo will download a small (~80MB) embedding model
from Hugging Face : needs internet once, then it's cached locally and
runs offline after that.

---

## Practice: Split Sample Documents into Chunks (`chunk_documents.py`)

Splits text into overlapping word-count-based chunks. Includes two
short sample documents (about RAG and embeddings) so the script runs
standalone without needing external files.

**Run it:**
```bash
python chunk_documents.py
```

**Why overlap matters:** without overlap, a sentence that happens to
fall right at a chunk boundary gets cut in half, and neither resulting
chunk has the full idea. Overlap (here, 8 words) means the end of one
chunk repeats at the start of the next, so boundary sentences survive
intact in at least one chunk. You can see this in `chunk_output_sample.txt`
: the phrase "what the model learned during training, RAG retrieves"
appears at the end of Chunk 1 and the start of Chunk 2.

**Note on chunking strategy:** this script chunks by word count for
simplicity. Production RAG systems more often chunk by token count
(since that's what actually fills the model's context window) or by
sentence/paragraph boundaries (to avoid splitting mid-sentence at all).
Word-count chunking is a reasonable first version to understand the
concept before adding that complexity.

---

## Practice + Deliverable: Mini Document Search Demo (`document_search_demo.py`)

Ties chunking, embedding, and similarity search into one interactive
CLI tool:

1. Loads the same sample documents, chunks them
2. Embeds every chunk using `all-MiniLM-L6-v2`
3. Takes a typed query, embeds it the same way
4. Ranks all chunks by cosine similarity to the query
5. Returns the top 3 most relevant chunks, with their similarity scores

**Run it:**
```bash
python document_search_demo.py
```

**Example session (illustrative : exact scores depend on the model run):**
```
Search query: how does RAG reduce hallucination?

Top 3 matches for: "how does RAG reduce hallucination?"
------------------------------------------------------------
#1 | score: 0.6xx | from: doc_rag.txt
   helps reduce hallucination because the model can ground its answer
   in real retrieved text rather than guessing from memory...

#2 | score: 0.4xx | from: doc_rag.txt
   ...
```

Type `quit` to exit.

### Why this counts as "search," not keyword matching
The query above doesn't share many exact words with the matched chunk
("reduce hallucination" does appear, but "how does X" and "ground...
in real retrieved text" share no words at all). The match comes from
**semantic similarity** the embedding model places texts with
related meaning close together in vector space, which is the whole
point of embeddings over plain keyword search.

## What this covers from Week 6
- **What embeddings are** : numeric vectors capturing meaning, generated
  by `model.encode()`
- **Similarity search**: cosine similarity ranks chunks by closeness
  to the query vector
- **Vector databases overview** : this demo uses a plain Python list as
  the "index," which is fine at this scale (a handful of chunks); a
  real vector database (Pinecone, Chroma, FAISS) becomes necessary once
  you have thousands+ of chunks and need fast approximate search
- **Chunking documents** : `chunk_documents.py`, with overlap to avoid
  losing context at boundaries
- **Why retrieval matters** : the demo's top match is grounded in actual
  document text, not the model guessing from memory (the same point
  made in the Week 5 notes about hallucination risk)


