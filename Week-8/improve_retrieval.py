"""
Week 8 Practice: Improve Retrieval with Better Chunking or Prompts

Two concrete improvements over the Week 7 prototype, motivated
directly by failure modes expected from evaluate_answers.py:

IMPROVEMENT 1 — Similarity score threshold
  Week 7's pipeline always sends the top-k chunks to the LLM, even if
  none of them are actually relevant (e.g. the "capital of France"
  question still retrieves SOMETHING, just with a low score). This
  adds a minimum similarity threshold: if the top score is below it,
  skip generation entirely and say so — instead of trusting the LLM's
  prompt instruction alone to refuse.

IMPROVEMENT 2 — Stricter, citation-aware prompt
  The Week 7 prompt asked the model to use "only the context" but
  didn't require it to say WHICH part of the context supported each
  claim. This version requires the model to cite the source document
  name for each claim, which makes faithfulness easier to check by
  eye (a human reviewer can verify the citation matches the context).

Both changes are demonstrated here in isolation so the before/after
difference is clear. The combined, final version lives in
rag_bot_v2.py (the deliverable).
"""

import os

from dotenv import load_dotenv

from chunk_documents import load_sample_documents
from retrieval import load_model, build_index, retrieve

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

load_dotenv()

# Chosen empirically: scores are written into evaluation_notes.md once
# the real model has been run. 0.3 is a reasonable starting point for
# all-MiniLM-L6-v2 cosine similarity scores on short text, and should
# be tuned after seeing real scores on your own documents/questions.
MIN_SIMILARITY_THRESHOLD = 0.3


def assemble_context_with_labels(results):
    """
    Same as Week 7's assemble_context, but numbers each source so the
    improved prompt can ask the model to cite by number.
    """
    parts = []
    for i, (score, record) in enumerate(results, start=1):
        parts.append(f"[Source {i}: {record['doc_name']}]\n{record['chunk_text']}")
    return "\n\n".join(parts)


def generate_answer_with_citations(question, context):
    """
    IMPROVEMENT 2: stricter prompt that requires citing source numbers
    for every claim, making faithfulness checkable by eye.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return None

    client = genai.Client(api_key=api_key)
    prompt = (
        "Answer the question using ONLY the numbered sources below. "
        "For every claim you make, cite the source number it came "
        "from, like this: (Source 1). "
        "If the sources don't contain the answer, say so explicitly "
        "and do not guess or use outside knowledge.\n\n"
        f"Sources:\n{context}\n\n"
        f"Question: {question}"
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"temperature": 0.2},
    )
    return response.text


def answer_with_threshold(model, index, question, top_k=3):
    """
    IMPROVEMENT 1: applies a minimum similarity threshold before
    even attempting generation.
    """
    retrieved = retrieve(model, index, question, top_k=top_k)
    top_score = retrieved[0][0]

    print(f"\nQuestion: {question}")
    print(f"Top retrieval score: {top_score:.3f} (threshold: {MIN_SIMILARITY_THRESHOLD})")

    if top_score < MIN_SIMILARITY_THRESHOLD:
        print("-> Below threshold. Skipping generation, returning honest 'no answer'.")
        print(
            "Answer: I don't have relevant information in my documents "
            "to answer that question."
        )
        return

    context = assemble_context_with_labels(retrieved)
    print("-> Above threshold. Generating cited answer.")
    print("-" * 60)
    print("Sources:")
    print(context)
    print("-" * 60)

    answer = generate_answer_with_citations(question, context)
    if answer is not None:
        print("Answer:")
        print(answer)
    else:
        print("[No GEMINI_API_KEY set — generation skipped.]")


def main():
    print("Loading embedding model...")
    model = load_model()

    documents = load_sample_documents()
    index = build_index(model, documents)
    print(f"Index ready: {len(index)} chunks.\n")

    test_questions = [
        "What is RAG and how does it reduce hallucination?",  # answerable
        "What is the capital of France?",  # unanswerable - should hit threshold
    ]

    for question in test_questions:
        answer_with_threshold(model, index, question)


if __name__ == "__main__":
    main()
