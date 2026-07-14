"""
Week 7 Practice: Test Different Chunk Sizes

Runs the same documents and the same query through several different
chunk sizes, to see how chunk size affects what gets retrieved.

Small chunks -> more precise, but can lose surrounding context
Large chunks -> more context per chunk, but less precise (a match
                might be "buried" in a lot of irrelevant text)
"""

from chunk_documents import load_sample_documents
from retrieval import load_model, build_index, retrieve

CHUNK_SIZES_TO_TEST = [15, 30, 60]  # words per chunk
TEST_QUERY = "how does RAG reduce hallucination?"


def run_test_for_chunk_size(model, documents, chunk_size):
    # overlap scales with chunk size so smaller chunks don't lose
    # proportionally more context at boundaries
    overlap = max(2, chunk_size // 4)

    index = build_index(model, documents, chunk_size=chunk_size, overlap=overlap)
    results = retrieve(model, index, TEST_QUERY, top_k=1)

    score, top_match = results[0]

    print(f"\nChunk size: {chunk_size} words (overlap: {overlap})")
    print(f"Total chunks created: {len(index)}")
    print(f"Top match score: {score:.3f}")
    print(f"Top match text ({len(top_match['chunk_text'].split())} words):")
    print(f"  {top_match['chunk_text']}")


def main():
    print("Loading embedding model...")
    model = load_model()

    documents = load_sample_documents()
    print(f"Query for all tests: \"{TEST_QUERY}\"")

    for chunk_size in CHUNK_SIZES_TO_TEST:
        run_test_for_chunk_size(model, documents, chunk_size)


if __name__ == "__main__":
    main()
