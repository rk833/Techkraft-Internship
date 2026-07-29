"""
Module 06 mini project: Sentence Similarity Checker.

Turns sentences into vectors and compares them, showing what embeddings
actually measure.

    pair    cosine similarity between two sentences you supply
    demo    a fixed set of comparisons that show what embeddings capture
    search  rank a file of sentences against a query
    matrix  every sentence in a file compared with every other

Every mode embeds all its text in a single batched request, so a run costs one
API call regardless of how many sentences are involved.

Usage:
    python similarity_checker.py --mode demo
    python similarity_checker.py --mode pair "a cat sat on the mat" "a feline rested on the rug"
    python similarity_checker.py --mode search --query "money" --file sample_sentences.txt
    python similarity_checker.py --mode matrix --file sample_sentences.txt
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_embedding_model, describe_api_error, embed_with_fallback

# Pairs chosen to show three different things, so the numbers can be compared
# against an expectation rather than just read.
DEMO_PAIRS = [
    (
        "same meaning, no shared words",
        "The bank approved my loan application.",
        "My mortgage was accepted by the lender.",
    ),
    (
        "shared word, different meaning",
        "The bank approved my loan application.",
        "I sat on the river bank watching the water.",
    ),
    (
        "shared word, different meaning",
        "Python is a popular programming language.",
        "The python coiled around the branch.",
    ),
    (
        "related topic",
        "She trained a model to predict rainfall.",
        "The forecast says it will rain tomorrow.",
    ),
    (
        "unrelated",
        "The bank approved my loan application.",
        "He forgot to water the plants.",
    ),
    (
        "identical text",
        "The server crashed under heavy load.",
        "The server crashed under heavy load.",
    ),
]


def normalise(vector: np.ndarray) -> np.ndarray:
    """
    Scale a vector to unit length.

    gemini-embedding-001 returns unit length vectors at its full 3072
    dimensions, but NOT when output_dimensionality truncates them. Measured
    norms were 1.000 at 3072, 0.693 at 1536 and 0.578 at 768.

    Cosine similarity divides by the norms so it survives either way, but a
    plain dot product does not, and most vector databases use dot product.
    Normalising here means the vectors are safe for both.
    """
    norm = np.linalg.norm(vector)
    return vector if norm == 0 else vector / norm


def embed(texts: list, task_type: str = None) -> np.ndarray:
    """
    Embed every text in one batched request.

    embed_documents sends the whole list together, so cost depends on the
    number of calls rather than the number of sentences.
    """
    vectors = embed_with_fallback(
        lambda embeddings: embeddings.embed_documents(texts), task_type=task_type
    )
    return np.array([normalise(np.array(v)) for v in vectors])


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    The angle between two vectors, ignoring their length.

    Length carries little meaning for text embeddings, direction carries the
    meaning, which is why cosine is used rather than euclidean distance.
    For unit length vectors this is just the dot product.
    """
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def label_for(score: float) -> str:
    """
    A rough reading of a score.

    These thresholds are calibrated to measured output from
    gemini-embedding-001 and are not general. That model's scores sit in a
    narrow band: a completely unrelated pair still scores about 0.75, and
    nothing observed fell below 0.7. Applying the textbook idea that 0.5 means
    unrelated would mark every pair here as a strong match.

    Recalibrate before trusting these numbers with a different model, by
    scoring a few pairs whose answer you already know.
    """
    if score >= 0.95:
        return "near identical"
    if score >= 0.85:
        return "same meaning"
    if score >= 0.80:
        return "related"
    if score >= 0.75:
        return "weakly related"
    return "unrelated"


def read_sentences(path: Path) -> list:
    if not path.exists():
        raise ConfigError(f"file not found: {path}")
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    sentences = [line for line in lines if line]
    if len(sentences) < 2:
        raise ConfigError(f"{path} needs at least two non-empty lines")
    return sentences


def run_pair(first: str, second: str) -> None:
    vectors = embed([first, second])
    score = cosine_similarity(vectors[0], vectors[1])

    print(f"model:      {active_embedding_model()}")
    print(f"dimensions: {vectors.shape[1]}")
    print()
    print(f"a: {first}")
    print(f"b: {second}")
    print()
    print(f"cosine similarity: {score:.4f}  ({label_for(score)})")


def run_demo() -> None:
    """All demo sentences embedded in one call, then compared."""
    texts = []
    for _, first, second in DEMO_PAIRS:
        texts.extend([first, second])

    vectors = embed(texts)
    print(f"model: {active_embedding_model()}, dimensions: {vectors.shape[1]}")
    print(f"{len(texts)} sentences embedded in a single request")
    print()

    # sorted, because the ranking is the reliable signal. The absolute values
    # sit in a narrow band and mean little on their own.
    scored = [
        (cosine_similarity(vectors[i * 2], vectors[i * 2 + 1]), note, first, second)
        for i, (note, first, second) in enumerate(DEMO_PAIRS)
    ]
    scored.sort(key=lambda row: row[0], reverse=True)

    for score, note, first, second in scored:
        print(f"{score:.4f}  {label_for(score):<15} {note}")
        print(f"          a: {first}")
        print(f"          b: {second}")
        print()

    spread = scored[0][0] - scored[-1][0]
    print("Two things to take from this, in order of importance.")
    print()
    print("The pair with the same meaning and almost no shared vocabulary should")
    print("outrank both pairs that share a word but mean different things. That")
    print("gap is the whole reason embeddings beat keyword matching.")
    print()
    print(f"Every score here falls between {scored[-1][0]:.2f} and {scored[0][0]:.2f},")
    print(f"a spread of only {spread:.2f}. Even the unrelated pair scores about 0.75.")
    print("So the ranking is meaningful but the absolute number is not. Do not")
    print("copy a threshold like 'similar means above 0.5' from a tutorial.")


def run_search(query: str, sentences: list, top: int) -> None:
    """
    Semantic search.

    The query and the documents are embedded with different task_type values,
    because Gemini positions a question differently from the passage that
    answers it. Two calls instead of one, and worth it for retrieval.
    """
    document_vectors = embed(sentences, task_type="RETRIEVAL_DOCUMENT")
    query_vector = embed([query], task_type="RETRIEVAL_QUERY")[0]

    scored = [
        (cosine_similarity(query_vector, vector), sentence)
        for vector, sentence in zip(document_vectors, sentences)
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    print(f"query: {query}")
    print(f"searching {len(sentences)} sentences")
    print()
    for score, sentence in scored[:top]:
        print(f"{score:.4f}  {sentence}")

    print()
    print("Note that matches are ranked by meaning, so a sentence can rank top")
    print("without containing the query word at all.")


def run_matrix(sentences: list, width: int) -> None:
    vectors = embed(sentences)
    count = len(sentences)

    print("similarity matrix")
    print()
    header = "     " + "".join(f"{i:>7}" for i in range(count))
    print(header)
    for row in range(count):
        cells = "".join(
            f"{cosine_similarity(vectors[row], vectors[column]):>7.3f}"
            for column in range(count)
        )
        print(f"{row:>3}  {cells}")

    print()
    for index, sentence in enumerate(sentences):
        text = sentence if len(sentence) <= width else sentence[:width] + "..."
        print(f"{index:>3}  {text}")

    # the strongest pair excluding the diagonal, which is always 1.0
    best = max(
        (
            (cosine_similarity(vectors[i], vectors[j]), i, j)
            for i in range(count)
            for j in range(i + 1, count)
        ),
        default=None,
    )
    if best:
        score, i, j = best
        print()
        print(f"closest pair: {i} and {j} at {score:.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare sentences by meaning using embeddings."
    )
    parser.add_argument(
        "sentences", nargs="*", help="two sentences, for --mode pair"
    )
    parser.add_argument(
        "--mode",
        choices=("pair", "demo", "search", "matrix"),
        default="demo",
    )
    parser.add_argument("--query", help="search query, for --mode search")
    parser.add_argument(
        "--file",
        default="sample_sentences.txt",
        help="one sentence per line, for search and matrix",
    )
    parser.add_argument("--top", type=int, default=5, help="results to show")
    parser.add_argument(
        "--width", type=int, default=60, help="sentence width in the matrix legend"
    )
    parser.add_argument("--debug", action="store_true", help="show the full traceback")
    args = parser.parse_args()

    try:
        if args.mode == "pair":
            if len(args.sentences) != 2:
                parser.error("--mode pair needs exactly two sentences")
            run_pair(args.sentences[0], args.sentences[1])
        elif args.mode == "demo":
            run_demo()
        elif args.mode == "search":
            if not args.query:
                parser.error("--mode search needs --query")
            run_search(args.query, read_sentences(Path(args.file)), args.top)
        else:
            run_matrix(read_sentences(Path(args.file)), args.width)
    except ConfigError as error:
        print(error)
        return 1
    except Exception as error:
        if args.debug:
            raise
        print(describe_api_error(error, active_embedding_model()))
        print()
        print("run again with --debug to see the full traceback")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
