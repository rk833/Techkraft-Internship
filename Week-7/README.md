# Week 7: RAG Pipeline Basics

## Practice
- Build a simple Q&A flow using documents
- Test different chunk sizes

## Deliverable
- Basic RAG prototype

## Overview
This week completes the RAG loop started in Week 6. Retrieval
(chunking + embedding + similarity search) is fully local and needs
no API key, same as last week. 

## Setup status

`qa_flow.py` and `rag_prototype.py` call the Gemini API for the
generation step, and **gracefully fall back** to showing retrieved
context only if no key is found so the scripts are still fully
runnable even before a key is added.

The API key is loaded from a **`.env` file**, not a shell environment
variable, so it never has to be typed into the terminal or committed
to GitHub.

```bash
pip install -r requirements.txt
```

### Getting a free Gemini API key
1. Go to [aistudio.google.com](https://aistudio.google.com) and sign
   in with a Google account
2. Open **Get API key** → **Create API key in new project**
3. Copy the key

### Setting up the .env file
1. Copy `.env.example` to a new file named `.env`:
   ```bash
   copy .env.example .env        # Windows
   cp .env.example .env          # Mac/Linux
   ```
2. Open `.env` and replace `your-key-here` with the real key:
   ```
   GEMINI_API_KEY=AIza...actual-key-goes-here
   ```
3. Save the file. No terminal restart or `setx`/`export` needed —
   `load_dotenv()` at the top of each script reads it automatically.

**`.env` is listed in `.gitignore` and will never be pushed to
GitHub.** `.env.example` (no real key, safe to commit) shows the
expected format for anyone else setting up the project.

First run of any script also downloads a small (~80MB) embedding
model from Hugging Face needs internet once, then it's cached
locally and works offline after that.

**Free tier note:** `gemini-2.5-flash` has generous free-tier limits
(no credit card needed), but Google's free-tier limits do change over
time and by region/account if you hit a `429` rate-limit error, wait
a bit and try again rather than assuming something's broken.

## Files
| File | Type | Covers |
|---|---|---|
| `chunk_documents.py` | Shared (from Week 6) | Document chunking |
| `retrieval.py` | Shared module | Embedding + similarity search, reused by everything below |
| `qa_flow.py` | Practice | Simple Q&A flow using documents |
| `test_chunk_sizes.py` | Practice | Test different chunk sizes |
| `chunk_size_test_notes.md` | Reference | Real results from the chunk size tests |
| `rag_prototype.py` | **Deliverable** | Interactive basic RAG prototype |
| `requirements.txt` | Shared | Dependencies |
| `.env.example` | Shared | Template showing the expected `.env` format (safe to commit) |
| `.gitignore` | Shared | Keeps the real `.env` out of GitHub |

---

## Practice: Simple Q&A Flow (`qa_flow.py`)

Runs the full RAG loop retrieve, assemble context, generate answer 
against three fixed test questions, including one deliberately
**off-topic** question ("What is the capital of France?") to test what
happens when the documents don't contain the answer.

**Run it:**
```bash
python qa_flow.py
```

**Why the off-topic question matters:** the sample documents are about
RAG and embeddings nothing about France. A good RAG system should
either retrieve weak/irrelevant matches (visible via low similarity
scores) or have the LLM explicitly say the context doesn't answer the
question, rather than the model falling back on its own training data
and answering anyway. The prompt in `generate_answer()` explicitly
instructs the model to say so honestly rather than guess directly
applying the hallucination-prevention idea from Week 5's notes.

---

## Practice: Test Different Chunk Sizes (`test_chunk_sizes.py`)

Builds three separate indexes (chunk sizes 15, 30, 60 words) from the
same documents, and runs the same query against each, to compare chunk
counts, top matches, and similarity scores.

**Run it:**
```bash
python test_chunk_sizes.py
```

See `chunk_size_test_notes.md` for the real, verified results
chunk-count scaling has been confirmed by actually running the code;
retrieval-quality comparison across chunk sizes is written and ready
to run with the embedding model.

---

## Deliverable: Basic RAG Prototype (`rag_prototype.py`)

An interactive CLI version of the Q&A flow same pipeline as
`qa_flow.py`, but takes live typed questions in a loop instead of a
fixed test list, so it's demoable.

**Run it:**
```bash
python rag_prototype.py
```

**Example session (retrieval-only, no API key):**
```
Question: how does RAG reduce hallucination?

Retrieved context:
------------------------------------------------------------
[From doc_rag.txt]
helps reduce hallucination because the model can ground its answer
in real retrieved text rather than guessing from memory...
------------------------------------------------------------

Question: quit
Goodbye.
```

With `GEMINI_API_KEY` set, a generated "Answer:" section appears below
the retrieved context, written using only that context.

## What this covers from Week 7
- **RAG architecture** — the full retrieve → assemble → generate loop
  is implemented in `rag_prototype.py`
- **Document loading** — `load_sample_documents()` (reused from Week 6)
- **Chunking strategy** — `test_chunk_sizes.py` and its notes compare
  three strategies directly
- **Embedding + retrieval flow** — `retrieval.py`, reused across every
  script this week
- **Context assembly for the LLM** — `assemble_context()`, which labels
  each chunk with its source document before handing it to the model

