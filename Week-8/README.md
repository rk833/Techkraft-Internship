# Week 8: RAG Quality and Evaluation

## Practice
- Evaluate answers on a small question set
- Improve retrieval with better chunking or prompts

## Deliverable
- Improved RAG bot with evaluation notes

## Overview
This week closes out Month 2 by measuring whether the Week 7 RAG
prototype actually works well, then fixing what's found. It reuses
`chunk_documents.py` and `retrieval.py` from Week 7 rather than
rebuilding them.

## Setup status
Same as Week 7 retrieval runs fully locally, generation uses the
Gemini free tier via a `.env` file. See "Setup" below.

## Files
| File | Type | Covers |
|---|---|---|
| `chunk_documents.py` | Shared (from Week 6/7) | Document chunking |
| `retrieval.py` | Shared (from Week 7) | Embedding + similarity search |
| `evaluate_answers.py` | Practice | Evaluate answers on a small question set |
| `improve_retrieval.py` | Practice | Improve retrieval with thresholds + better prompts |
| `rag_bot_v2.py` | **Deliverable** | Improved RAG bot combining both fixes |
| `evaluation_notes.md` | **Deliverable** | Scoring rubric, worked example, results table |
| `requirements.txt` | Shared | Dependencies |
| `.env.example` / `.gitignore` | Shared | Same `.env` key setup as Week 7 |

---

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env        # Windows
# cp .env.example .env        # Mac/Linux
```
Then open `.env` and add your real Gemini key (see Week 7's README
for how to get one free from [aistudio.google.com](https://aistudio.google.com)).

---

## Practice: Evaluate Answers on a Small Question Set (`evaluate_answers.py`)

Runs 5 deliberately varied test questions through the RAG pipeline:
two fully **answerable** from the sample documents, one **partially
answerable** (tests whether the model invents specifics not actually
supported), and two **unanswerable** (test whether the model honestly
refuses instead of hallucinating from its own training knowledge).

**Run it:**
```bash
python evaluate_answers.py
```

For each question it prints the retrieval score, retrieved context,
and generated answer ready for manual scoring against the rubric in
`evaluation_notes.md`.

**Why include unanswerable questions on purpose:** if every test
question has a clean answer in the documents, faithfulness failures
(the model quietly using its own knowledge instead of the retrieved
context) are invisible. The "capital of France" and "which vector
database" questions exist specifically to surface that failure mode.

---

## Practice: Improve Retrieval with Better Chunking or Prompts (`improve_retrieval.py`)

Two specific improvements, demonstrated and tested separately before
being combined into the deliverable:

1. **Similarity score threshold** — checks the top retrieval score
   *before* calling the LLM. If nothing relevant was found, returns an
   honest "no answer" without spending an API call or risking the
   model ignoring its instructions.
2. **Citation-aware prompt** — requires every claim in the answer to
   cite a numbered source, making faithfulness checkable by eye
   instead of requiring a manual side-by-side comparison.

**Run it:**
```bash
python improve_retrieval.py
```

See `evaluation_notes.md` for the reasoning behind these two specific
fixes and why they target real failure modes rather than generic
"make it better" changes.

---

## Deliverable: Improved RAG Bot v2 (`rag_bot_v2.py`)

Combines both improvements into one interactive bot — the direct
successor to Week 7's `rag_prototype.py`.

**Run it:**
```bash
python rag_bot_v2.py
```

**What changed from v1:**
- Won't attempt to answer if retrieval didn't find anything relevant
  (threshold check, not just a prompt instruction)
- Every answer cites which source(s) it drew from

## What this covers from Week 8
- **Common RAG failure modes** — the unanswerable test questions
  specifically target the "model ignores context and uses its own
  knowledge" failure
- **Retrieval quality vs answer quality** — the evaluation rubric
  scores these separately (relevance = retrieval, accuracy/faithfulness
  = generation), so problems can be traced to the right stage
- **Relevance, accuracy, and faithfulness** — the three-axis scoring
  rubric in `evaluation_notes.md`
- **Adding citations or sources** — `rag_bot_v2.py`'s numbered-source
  citation requirement
- **Debugging bad answers** — the worked example in
  `evaluation_notes.md` walks through diagnosing exactly what a bad
  answer to an unanswerable question would mean



