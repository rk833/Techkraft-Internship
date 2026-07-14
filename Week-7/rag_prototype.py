"""
Week 7 Deliverable: Basic RAG Prototype

An interactive command-line RAG prototype. This is the same pipeline
as qa_flow.py, packaged as a standalone, demoable tool rather than a
fixed list of test questions.

Pipeline:
    documents -> chunk -> embed -> build index   (done once, at startup)
    user question -> embed -> retrieve top chunks -> assemble context
    -> generate answer with LLM (if API key available)

Run:
    python rag_prototype.py
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
    parts = [f"[From {record['doc_name']}]\n{record['chunk_text']}" for _, record in results]
    return "\n\n".join(parts)


def generate_answer(question, context):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key or not GEMINI_AVAILABLE:
        return None

    client = genai.Client(api_key=api_key)

    prompt = (
        "Answer the question using ONLY the context below. "
        "If the context doesn't contain the answer, say so honestly.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.2},
        )

        return response.text

    except Exception as error:
        if "503" in str(error):
            return (
            "Gemini is currently busy (503 Service Unavailable). "
            "Please try again in a few minutes."
        )

    return f"API Error: {error}"

def main():
    print("=" * 60)
    print("Basic RAG Prototype")
    print("=" * 60)

    print("\nLoading embedding model...")
    model = load_model()

    documents = load_sample_documents()
    print(f"Building index from {len(documents)} document(s)...")
    index = build_index(model, documents)
    print(f"Ready. Index contains {len(index)} chunks.\n")

    if not (os.environ.get("GEMINI_API_KEY") and GEMINI_AVAILABLE):
        print(
            "[Note: no GEMINI_API_KEY set, so this will show retrieved "
            "context only, not a generated answer. See README.]\n"
        )

    print("Ask a question about RAG or embeddings. Type 'quit' to exit.\n")

    while True:
        question = input("Question: ").strip()
        if question.lower() in ("quit", "exit"):
            print("Goodbye.")
            break
        if not question:
            continue

        results = retrieve(model, index, question, top_k=3)
        context = assemble_context(results)

        print("\nRetrieved context:")
        print("-" * 60)
        print(context)
        print("-" * 60)

        answer = generate_answer(question, context)
        if answer is not None:
            print("\nAnswer:")
            print(answer)
        print()


if __name__ == "__main__":
    main()
