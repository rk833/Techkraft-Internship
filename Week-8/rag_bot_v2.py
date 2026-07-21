"""
Week 8 Deliverable: Improved RAG Bot (v2)

This is rag_prototype.py (Week 7) improved with the two changes
developed and tested in improve_retrieval.py:

  1. Similarity score threshold — refuses to generate an answer when
     retrieval didn't find anything actually relevant, instead of
     trusting the prompt instruction alone
  2. Citation-aware prompt — every claim in the answer is tagged with
     the source it came from, making faithfulness checkable by eye

See evaluation_notes.md for before/after evaluation results comparing
this version against the Week 7 prototype.

Run:
    python rag_bot_v2.py
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

MIN_SIMILARITY_THRESHOLD = 0.3


def assemble_context_with_labels(results):
    parts = []
    for i, (score, record) in enumerate(results, start=1):
        parts.append(f"[Source {i}: {record['doc_name']}]\n{record['chunk_text']}")
    return "\n\n".join(parts)


def generate_answer_with_citations(question, context):
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


def answer_question(model, index, question, top_k=3):
    retrieved = retrieve(model, index, question, top_k=top_k)
    top_score = retrieved[0][0]

    print(f"\nTop retrieval score: {top_score:.3f}")

    if top_score < MIN_SIMILARITY_THRESHOLD:
        print(
            "I don't have relevant information in my documents to "
            "answer that question."
        )
        return

    context = assemble_context_with_labels(retrieved)
    print("\nSources used:")
    print("-" * 60)
    print(context)
    print("-" * 60)

    answer = generate_answer_with_citations(question, context)
    if answer is not None:
        print("\nAnswer:")
        print(answer)
    else:
        print(
            "[No GEMINI_API_KEY set — showing sources only, no "
            "generated answer. See README.]"
        )


def main():
    print("=" * 60)
    print("Improved RAG Bot (v2)")
    print("Changes from v1: similarity threshold + cited answers")
    print("=" * 60)

    print("\nLoading embedding model...")
    model = load_model()

    documents = load_sample_documents()
    print(f"Building index from {len(documents)} document(s)...")
    index = build_index(model, documents)
    print(f"Ready. Index contains {len(index)} chunks.\n")

    print("Ask a question. Type 'quit' to exit.\n")

    while True:
        question = input("Question: ").strip()
        if question.lower() in ("quit", "exit"):
            print("Goodbye.")
            break
        if not question:
            continue

        answer_question(model, index, question)
        print()


if __name__ == "__main__":
    main()
