# Week 8 — Evaluation Notes

## Scoring rubric

Each answer from `evaluate_answers.py` is scored 1-3 on three axes,
matching this week's topics:

| Score | Relevance | Accuracy | Faithfulness |
|---|---|---|---|
| **3** | Retrieved chunks are directly about the question | Answer matches what the source documents actually say | Every claim is traceable to retrieved context |
| **2** | Retrieved chunks are loosely related | Answer is mostly correct but missing nuance or slightly off | Answer mostly sticks to context, with minor unsupported additions |
| **1** | Retrieved chunks are unrelated to the question | Answer is wrong or contradicts the source documents | Answer relies mainly on the model's own outside knowledge, not the retrieved context |

**Relevance** is about retrieval (did the embedding search find the
right chunks). **Accuracy** and **faithfulness** are about generation
(did the LLM use those chunks correctly). This separation matters
because a bad answer could come from either stage — scoring both
separately makes debugging much faster, directly addressing this
week's "Retrieval quality vs answer quality" topic.

---

## Status: results pending real execution

I don't have internet access to Hugging Face or the Gemini API in
this environment, so I can't generate real retrieval scores or model
answers myself this week (same constraint as Weeks 6 and 7). What's
below is:
1. A **worked example** of how to apply the rubric, using reasoning
   about what should happen for one of the test questions
2. A **template table** to fill in once `evaluate_answers.py` is run
   for real

### Worked example: the "capital of France" question

This question is deliberately unanswerable from the sample documents
(which only cover RAG and embeddings). Reasoning through what *should*
happen with the Week 7 prototype vs. the rubric:

- **Relevance: expected 1.** Nothing in either sample document relates
  to France or capitals, so the top retrieved chunk should have a
  low similarity score and be about RAG/embeddings, not geography.
- **Accuracy: expected 3, conditionally.** If the model follows the
  "say so honestly" instruction in the prompt, refusing to answer is
  itself the *correct* behavior — accuracy here means "did it avoid
  asserting a wrong-but-plausible-sounding answer," not "did it know
  Paris is the capital." (The model almost certainly knows that fact
  from training, which is exactly the risk — it could ignore the
  context instruction and answer from memory instead.)
- **Faithfulness: this is the real test.** If the model answers
  "Paris" despite empty/irrelevant context, that's a **faithfulness
  failure** — it ignored the RAG context and used outside training
  knowledge. If it says "the documents don't contain this
  information," that's faithfulness working correctly.

This is precisely why the question set includes intentionally
unanswerable questions: faithfulness failures are invisible if every
test question has a clean answer in the documents.

---

## Results table (fill in after running `evaluate_answers.py`)

| Question | Type | Top score | Relevance | Accuracy | Faithfulness | Notes |
|---|---|---|---|---|---|---|
| What is RAG and how does it reduce hallucination? | answerable | | | | | |
| What is cosine similarity used for? | answerable | | | | | |
| What chunk size should I always use for every document? | partially_answerable | | | | | Watch for the model inventing a specific number not actually supported by the docs |
| What is the capital of France? | unanswerable | | | | | Faithfulness test: see worked example above |
| Which vector database should I use for production RAG? | unanswerable | | | | | Docs mention vector DBs exist but recommend none specifically |

---

## Improvement applied (v1 → v2)

Based on the reasoning above (not yet confirmed with real scores),
two changes were made in `rag_bot_v2.py` versus the Week 7 prototype:

### 1. Similarity score threshold (`MIN_SIMILARITY_THRESHOLD = 0.3`)
**Problem this targets:** Week 7's bot always sends the top-k chunks
to the LLM, even when none of them are relevant, relying entirely on
the prompt instruction to refuse. That's a single point of failure 
if the model doesn't follow the instruction, there's no backstop.

**Fix:** check the top similarity score *before* calling the LLM at
all. Below threshold → return an honest "no answer" directly, no
generation call made. This is a code-level guardrail, not just a
prompt-level one.

**Caveat:** `0.3` is a starting estimate, not an empirically tuned
value — I haven't seen real similarity scores from this embedding
model yet. Once `evaluate_answers.py` is run for real, the actual
top-scores column above should be used to pick a threshold that
clearly separates "relevant" from "irrelevant" results for this
specific model and document set.

### 2. Citation-aware prompt
**Problem this targets:** the original prompt said "use only the
context" but gave no way to verify that from the output, a human
reviewer had to manually compare the answer against the context to
check faithfulness.

**Fix:** the new prompt requires every claim to cite a numbered
source, e.g. "RAG retrieves relevant documents at query time (Source
1)." This makes faithfulness checking much faster — a fabricated
claim either has no citation or cites a source that doesn't actually
support it, both of which are easy to spot by eye.

---

## What to do once this runs for real

1. Run `evaluate_answers.py`, fill in the results table above with
   real scores
2. Run `rag_bot_v2.py` against the same five questions, compare
   answers side by side with the v1 results
3. If the threshold of 0.3 is letting irrelevant chunks through (or
   blocking relevant ones), adjust it based on the real score
   distribution and note the change here
4. Spot-check a few citations in the v2 answers against the actual
   retrieved context to confirm they're accurate, not just present
