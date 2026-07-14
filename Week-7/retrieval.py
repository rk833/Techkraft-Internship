"""
Week 7: Shared Retrieval Module

Core embedding + retrieval logic, reused by both practice scripts and
the deliverable. This is the same approach as Week 6's
document_search_demo.py, pulled into its own module so it isn't
duplicated three times across this week's files.

Requires: sentence-transformers, numpy
"""

import numpy as np
from sentence_transformers import SentenceTransformer

from chunk_documents import chunk_text

MODEL_NAME = "all-MiniLM-L6-v2"


def cosine_similarity(vector_a, vector_b):
    vector_a = np.array(vector_a)
    vector_b = np.array(vector_b)
    return float(
        np.dot(vector_a, vector_b)
        / (np.linalg.norm(vector_a) * np.linalg.norm(vector_b))
    )


def load_model():
    """Load the embedding model once, reused across all calls."""
    return SentenceTransformer(MODEL_NAME)


def build_index(model, documents, chunk_size=30, overlap=8):
    """
    Chunk every document and embed every chunk.
    Returns a list of dicts: {doc_name, chunk_text, embedding}.
    """
    index = []
    for doc_name, doc_text in documents.items():
        chunks = chunk_text(doc_text, chunk_size=chunk_size, overlap=overlap)
        embeddings = model.encode(chunks)
        for chunk, embedding in zip(chunks, embeddings):
            index.append(
                {"doc_name": doc_name, "chunk_text": chunk, "embedding": embedding}
            )
    return index


def retrieve(model, index, query, top_k=3):
    """
    Embed the query and return the top_k most similar chunks,
    ranked by cosine similarity (highest first).
    """
    query_embedding = model.encode(query)
    scored = [
        (cosine_similarity(query_embedding, record["embedding"]), record)
        for record in index
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:top_k]
