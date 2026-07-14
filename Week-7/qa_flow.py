"""
Week 7 Practice: Build a Simple Q&A Flow Using Documents

This is the full RAG loop in its simplest form:

    question -> retrieve relevant chunks -> assemble context
             -> ask the LLM to answer USING that context -> answer

Retrieval (embeddings + similarity search) runs fully locally and
needs no API key, same as Week 6.

Answer generation uses Google's Gemini API (free tier: gemini-2.5-flash).
The API key is loaded from a .env file (see .env.example) rather than
a shell environment variable. If no key is found, this script falls
back to printing the retrieved context directly instead of a
generated answer, so it's still runnable and shows the retrieval half
of RAG working end to end.
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

load_dotenv()  # reads .env in the current directory and loads it into os.environ


def assemble_context(results):
    """
    Turn retrieved (score, record) pairs into a single text block
    to hand to the LLM as context. This is the "context assembly"
    step from this week's topics.
    """
    context_parts = []
    for score, record in results:
        context_parts.append(f"[From {record['doc_name']}]\n{record['chunk_text']}")
    return "\n\n".join(context_parts)


def generate_answer(question, context):
    """
    Ask the LLM to answer the question using ONLY the retrieved
    context. Returns None if no API key is available.
    """
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
        config={"temperature": 0.2},  # low temperature: factual task, not creative
    )
    return response.text


def answer_question(model, index, question, top_k=3):
    """Run the full retrieve -> assemble -> generate flow for one question."""
    results = retrieve(model, index, question, top_k=top_k)
    context = assemble_context(results)

    print(f"\nQuestion: {question}")
    print("-" * 60)
    print("Retrieved context:")
    print(context)
    print("-" * 60)

    answer = generate_answer(question, context)
    if answer is not None:
        print("Generated answer:")
        print(answer)
    else:
        print(
            "[No GEMINI_API_KEY set — skipping answer generation. "
            "Retrieved context above is what WOULD be sent to the "
            "LLM to generate an answer.]"
        )
    print()


def main():
    print("Loading embedding model...")
    model = load_model()

    documents = load_sample_documents()
    print(f"Building index from {len(documents)} document(s)...")
    index = build_index(model, documents)
    print(f"Index ready: {len(index)} chunks.\n")

    questions = [
        "What is RAG and how does it reduce hallucination?",
        "What is cosine similarity used for?",
        "What is the capital of France?",  # deliberately off-topic
    ]

    for question in questions:
        answer_question(model, index, question)


if __name__ == "__main__":
    main()
