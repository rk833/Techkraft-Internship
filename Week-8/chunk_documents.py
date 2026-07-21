"""
Week 6 Practice: Split Sample Documents into Chunks

Splits longer text documents into smaller overlapping chunks, which
is the first step of any RAG pipeline. Chunking matters because:
- Embedding models have a max input length
- Smaller chunks give more precise retrieval (less irrelevant text
  mixed into a match)
- Some overlap between chunks avoids cutting a key sentence in half
  right at a chunk boundary

This script works on plain text and chunks by WORD COUNT, which is
simple to reason about as a first pass (real systems often chunk by
tokens or sentences instead, see notes in README).
"""


def chunk_text(text, chunk_size=50, overlap=10):
    """
    Split text into overlapping chunks of `chunk_size` words.

    Args:
        text: the full document text
        chunk_size: number of words per chunk
        overlap: number of words shared between consecutive chunks

    Returns:
        A list of text chunks (strings).
    """
    words = text.split()
    chunks = []

    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))

        if end >= len(words):
            break

        # Move forward by (chunk_size - overlap) so the next chunk
        # repeats the last `overlap` words of this one.
        start += chunk_size - overlap

    return chunks


def load_sample_documents():
    """
    A few short sample documents to practice chunking on.
    In a real pipeline these would come from files, a database, or
    scraped pages — kept inline here so the script runs standalone.
    """
    return {
        "doc_rag.txt": (
            "Retrieval-Augmented Generation, or RAG, is a technique that "
            "combines a language model with an external knowledge source. "
            "Instead of relying only on what the model learned during "
            "training, RAG retrieves relevant documents at query time and "
            "feeds them into the model's context window. This helps reduce "
            "hallucination because the model can ground its answer in real "
            "retrieved text rather than guessing from memory. A typical RAG "
            "pipeline has three stages: chunking documents, embedding the "
            "chunks, and retrieving the most similar chunks for a given "
            "query. Chunk size matters a lot — chunks that are too large "
            "dilute relevance, while chunks that are too small lose context."
        ),
        "doc_embeddings.txt": (
            "An embedding is a numeric vector representation of text that "
            "captures its meaning. Texts with similar meaning end up with "
            "vectors that are close together in that vector space, even if "
            "they don't share any exact words. This is what makes semantic "
            "search possible — instead of matching exact keywords, you can "
            "find text that means the same thing. Embedding models are "
            "trained on large amounts of text so that semantically similar "
            "sentences land near each other geometrically. Cosine "
            "similarity is the most common way to measure how close two "
            "embedding vectors are to each other."
        ),
    }


if __name__ == "__main__":
    documents = load_sample_documents()

    for doc_name, doc_text in documents.items():
        print("=" * 60)
        print(f"DOCUMENT: {doc_name}")
        print(f"Word count: {len(doc_text.split())}")
        print("-" * 60)

        chunks = chunk_text(doc_text, chunk_size=30, overlap=8)

        for i, chunk in enumerate(chunks, start=1):
            print(f"\nChunk {i} ({len(chunk.split())} words):")
            print(chunk)

        print()
