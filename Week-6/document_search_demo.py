"""
Week 6 Practice + Deliverable: Mini Document Search Demo

This single script covers the last two practice items AND the
deliverable, since they form one natural pipeline:

  1. Create embeddings for text     (practice)
  2. Search similar chunks          (practice)
  3. Mini document search demo      (deliverable — tying it together)

Pipeline:
  documents -> chunk_text() -> embed each chunk -> store vectors
  -> embed the user's query -> cosine similarity against all chunks
  -> return the most similar chunk(s)

Requires: sentence-transformers, numpy
    pip install -r requirements.txt

"""

import numpy as np
from sentence_transformers import SentenceTransformer

from chunk_documents import load_sample_documents, chunk_text

MODEL_NAME = "all-MiniLM-L6-v2"  # small, fast, good enough for this demo


def cosine_similarity(vector_a, vector_b):
    """Return cosine similarity between two vectors (1.0 = identical
    direction, 0.0 = unrelated, -1.0 = opposite)."""
    vector_a = np.array(vector_a)
    vector_b = np.array(vector_b)
    return float(
        np.dot(vector_a, vector_b)
        / (np.linalg.norm(vector_a) * np.linalg.norm(vector_b))
    )


def build_chunk_index(model, documents, chunk_size=30, overlap=8):
    """
    Chunk every document, embed every chunk, and return a list of
    records so we know which document/chunk each embedding came from.
    """
    index = []  # list of dicts: {doc_name, chunk_text, embedding}

    for doc_name, doc_text in documents.items():
        chunks = chunk_text(doc_text, chunk_size=chunk_size, overlap=overlap)
        embeddings = model.encode(chunks)  # one embedding per chunk

        for chunk, embedding in zip(chunks, embeddings):
            index.append(
                {
                    "doc_name": doc_name,
                    "chunk_text": chunk,
                    "embedding": embedding,
                }
            )

    return index


def search(model, index, query, top_k=3):
    """
    Embed the query and return the top_k most similar chunks from
    the index, ranked by cosine similarity (highest first).
    """
    query_embedding = model.encode(query)

    scored = []
    for record in index:
        score = cosine_similarity(query_embedding, record["embedding"])
        scored.append((score, record))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:top_k]


def main():
    print("Loading embedding model (first run downloads ~80MB)...")
    model = SentenceTransformer(MODEL_NAME)

    documents = load_sample_documents()
    print(f"Chunking and embedding {len(documents)} document(s)...")
    index = build_chunk_index(model, documents)
    print(f"Index built: {len(index)} chunks total.\n")

    print("Mini Document Search Demo")
    print("Type a question about RAG or embeddings. Type 'quit' to exit.\n")

    while True:
        query = input("Search query: ").strip()
        if query.lower() in ("quit", "exit"):
            break
        if not query:
            continue

        results = search(model, index, query, top_k=3)

        print(f"\nTop {len(results)} matches for: \"{query}\"")
        print("-" * 60)
        for rank, (score, record) in enumerate(results, start=1):
            print(f"#{rank} | score: {score:.3f} | from: {record['doc_name']}")
            print(f"   {record['chunk_text']}\n")


if __name__ == "__main__":
    main()
