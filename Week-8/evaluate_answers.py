"""
Week 8 Practice: Evaluate Answers on a Small Question Set

A small but deliberately varied set of test questions, designed to
expose different RAG failure modes:

  - answerable: the documents contain a direct answer
  - partially_answerable: documents touch the topic but don't fully
    cover what's asked
  - unanswerable: the documents have nothing relevant at all
    (tests whether the bot honestly says "I don't know" instead of
    hallucinating from the LLM's own training knowledge)

This script runs the RAG pipeline (from Week 7 / retrieval.py) against
every question, then scores each answer along three axes asked for in
this week's topics:

  - relevance:   did retrieval pull back chunks actually related to
                  the question?
  - accuracy:    is the generated answer factually correct relative
                  to the source documents?
  - faithfulness: does the answer stick to what's actually in the
                  retrieved context, or does it add unsupported claims?

Scoring here is done by HUMAN judgment (you read the output and fill
in scores) rather than an automated metric that's appropriate at
this stage and is explicitly what "Evaluate answers on a small
question set" calls for. An automated LLM-as-judge approach is noted
as a possible improvement in the README.
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


# Each question is tagged with its expected difficulty/answerability,
# so results can be grouped and the failure modes are easy to spot.
EVAL_QUESTIONS = [
    {
        "question": "What is RAG and how does it reduce hallucination?",
        "type": "answerable",
    },
    {
        "question": "What is cosine similarity used for?",
        "type": "answerable",
    },
    {
        "question": "What chunk size should I always use for every document?",
        "type": "partially_answerable",
        # The docs discuss chunk size tradeoffs but never give a single
        # universal "always use X" answer — good test of whether the
        # bot invents a specific number that isn't actually supported.
    },
    {
        "question": "What is the capital of France?",
        "type": "unanswerable",
    },
    {
        "question": "Which vector database should I use for production RAG?",
        "type": "unanswerable",
        # The docs mention vector databases exist conceptually but
        # never recommend a specific product.
    },
]


def assemble_context(results):
    parts = [f"[From {record['doc_name']}]\n{record['chunk_text']}" for _, record in results]
    return "\n\n".join(parts)


def generate_answer(question, context):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not GEMINI_AVAILABLE:
        return None

    client = genai.Client(api_key=api_key)
    prompt = (
        "Answer the question using ONLY the context below. "
        "If the context doesn't contain the answer, say so honestly "
        "rather than guessing.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"temperature": 0.2},
    )
    return response.text


def run_evaluation(model, index):
    """
    Run every question in EVAL_QUESTIONS through the RAG pipeline and
    print retrieval + generation output, ready for manual scoring.
    """
    results_log = []

    for item in EVAL_QUESTIONS:
        question = item["question"]
        expected_type = item["type"]

        retrieved = retrieve(model, index, question, top_k=3)
        context = assemble_context(retrieved)
        top_score = retrieved[0][0]

        answer = generate_answer(question, context)

        print("=" * 70)
        print(f"Question: {question}")
        print(f"Expected type: {expected_type}")
        print(f"Top retrieval score: {top_score:.3f}")
        print("-" * 70)
        print("Retrieved context:")
        print(context)
        print("-" * 70)
        if answer is not None:
            print("Generated answer:")
            print(answer)
        else:
            print("[No GEMINI_API_KEY set — generation skipped.]")
        print()

        results_log.append(
            {
                "question": question,
                "expected_type": expected_type,
                "top_score": top_score,
                "context": context,
                "answer": answer,
            }
        )

    return results_log


def main():
    print("Loading embedding model...")
    model = load_model()

    documents = load_sample_documents()
    print(f"Building index from {len(documents)} document(s)...\n")
    index = build_index(model, documents)

    run_evaluation(model, index)

    print("=" * 70)
    print(
        "Evaluation run complete. Score each answer for relevance, "
        "accuracy, and faithfulness — see evaluation_notes.md for the "
        "scoring rubric and filled-in results."
    )


if __name__ == "__main__":
    main()
