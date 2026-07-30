"""
Module 10 mini project: Search Comparison Demo.

Runs the same query through four retrieval strategies and shows how the
rankings differ.

    keyword   BM25, exact term matching, no embeddings and no API calls
    semantic  vector similarity, the approach used since Module 06
    hybrid    both of the above merged by reciprocal rank fusion
    reranked  hybrid results reordered by a local cross encoder

The point of the module is that keyword and semantic search fail in different
ways, so combining them beats either, and a reranker fixes what is left.

Only the semantic side costs anything: one call to embed the query. BM25 and
the cross encoder run locally.

Usage:
    python search_comparison.py build
    python search_comparison.py compare --query "ERR_4021"
    python search_comparison.py compare --query "why is the app so slow the first time"
    python search_comparison.py search --query "..." --method reranked
"""

import argparse
import logging
import shutil
import sys
import warnings
from pathlib import Path

from langchain_chroma import Chroma
from langchain_classic.retrievers import (
    ContextualCompressionRetriever,
    EnsembleRetriever,
)
from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_embedding_model, describe_api_error
from common.embeddings import build_embeddings
from common.models import api_keys

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from langchain_community.document_compressors import FlashrankRerank
    from langchain_community.retrievers import BM25Retriever

HERE = Path(__file__).resolve().parent
STORE_DIR = HERE / "chroma_db"
COLLECTION = "support"
METHODS = ("keyword", "semantic", "hybrid", "reranked")

# The cross encoder is downloaded on first use and cached. This one is about
# 4 MB. FlashRank's default, ms-marco-MultiBERT-L-12, is about 99 MB and scores
# a little better; set RERANK_MODEL to it if the extra accuracy is worth the
# download. Either way the model runs locally and costs no quota.
RERANK_MODEL = "ms-marco-TinyBERT-L-2-v2"

# flashrank and httpx both log at INFO, which buries the actual output
logging.getLogger("flashrank").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def embeddings_for(task_type: str):
    return build_embeddings(active_embedding_model(), api_keys()[0], task_type=task_type)


def parse_articles(path: Path) -> list:
    """Read the knowledge base into one Document per article."""
    if not path.exists():
        raise ConfigError(f"articles file not found: {path}")

    documents = []
    article_id = title = None
    body = []

    def flush():
        if article_id and body:
            documents.append(
                Document(
                    page_content=f"{title}. " + " ".join(body),
                    metadata={"id": article_id, "title": title},
                )
            )

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("[") and "]" in stripped:
            flush()
            article_id = stripped[1 : stripped.index("]")]
            title = stripped[stripped.index("]") + 1 :].strip()
            body = []
        elif stripped:
            body.append(stripped)

    flush()
    if not documents:
        raise ConfigError(f"no articles found in {path}")
    return documents


def build(path: Path, rebuild: bool) -> None:
    documents = parse_articles(path)
    print(f"parsed {len(documents)} articles")

    if rebuild:
        shutil.rmtree(STORE_DIR, ignore_errors=True)

    store = Chroma.from_documents(
        documents,
        embeddings_for("RETRIEVAL_DOCUMENT"),
        collection_name=COLLECTION,
        persist_directory=str(STORE_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )
    print(f"stored {store._collection.count()} vectors in {STORE_DIR.name}/")
    print()
    print("BM25 is not stored. It is built from the text file at query time,")
    print("because it is an index over words rather than vectors.")


def open_store() -> Chroma:
    if not STORE_DIR.exists():
        raise ConfigError("no index found. run 'python search_comparison.py build' first")
    return Chroma(
        collection_name=COLLECTION,
        persist_directory=str(STORE_DIR),
        embedding_function=embeddings_for("RETRIEVAL_QUERY"),
    )


def make_retriever(method: str, documents: list, top: int, rerank_model: str = None):
    """
    Build one retrieval strategy.

    keyword needs no store and no API calls at all. The others build on the
    Chroma index created by build.
    """
    if method == "keyword":
        # BM25 scores on term overlap, weighting rare words heavily and
        # penalising long documents. It has no idea what any word means.
        retriever = BM25Retriever.from_documents(documents)
        retriever.k = top
        return retriever

    semantic = open_store().as_retriever(search_kwargs={"k": top})
    if method == "semantic":
        return semantic

    bm25 = BM25Retriever.from_documents(documents)
    bm25.k = top

    # EnsembleRetriever merges by reciprocal rank fusion: each result scores
    # 1/(rank + constant) in every list it appears in, and those are summed.
    # It uses ranks rather than raw scores, which matters because BM25 scores
    # and cosine distances are not on any comparable scale.
    hybrid = EnsembleRetriever(retrievers=[bm25, semantic], weights=[0.5, 0.5])
    if method == "hybrid":
        return hybrid

    # A cross encoder reads the query and a document together and scores the
    # pair directly, instead of comparing two independently made vectors. It is
    # far more accurate and far too slow to run over a whole corpus, so it only
    # reorders what retrieval already narrowed down.
    return ContextualCompressionRetriever(
        base_compressor=FlashrankRerank(model=rerank_model or RERANK_MODEL, top_n=top),
        base_retriever=hybrid,
    )


def run(method: str, query: str, documents: list, top: int, rerank_model: str = None) -> list:
    return make_retriever(method, documents, top, rerank_model).invoke(query)


def show(method: str, query: str, documents: list, top: int, rerank_model: str = None) -> None:
    hits = run(method, query, documents, top, rerank_model)

    print(f"query:  {query}")
    print(f"method: {method}")
    print()
    if not hits:
        print("  nothing retrieved")
        return
    for index, document in enumerate(hits):
        print(f"  {index + 1}. [{document.metadata['id']}] {document.metadata['title']}")


def compare(query: str, documents: list, top: int, rerank_model: str = None) -> None:
    """
    Same query through every method, ranked lists side by side.

    Only the article id is shown, so the orderings can be compared at a glance.
    """
    results = {}
    for method in METHODS:
        try:
            results[method] = [d.metadata["id"] for d in run(method, query, documents, top, rerank_model)]
        except Exception as error:
            results[method] = [f"failed: {type(error).__name__}"]

    print(f"query: {query}")
    print()

    header = "rank  " + "".join(f"{m:<12}" for m in METHODS)
    print(header)
    print("-" * len(header))
    for rank in range(top):
        cells = ""
        for method in METHODS:
            hits = results[method]
            cells += f"{hits[rank] if rank < len(hits) else '':<12}"
        print(f"{rank + 1:<6}{cells}")

    print()
    lookup = {d.metadata["id"]: d.metadata["title"] for d in documents}
    shown = []
    for method in METHODS:
        for article_id in results[method][:3]:
            if article_id in lookup and article_id not in shown:
                shown.append(article_id)
    for article_id in shown:
        print(f"  {article_id}  {lookup[article_id]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare keyword, semantic, hybrid and reranked search."
    )
    parser.add_argument("command", choices=("build", "search", "compare"))
    parser.add_argument("--query", help="what to search for")
    parser.add_argument("--method", choices=METHODS, default="hybrid")
    parser.add_argument("--file", default="support_articles.txt")
    parser.add_argument("--top", type=int, default=4)
    parser.add_argument(
        "--rerank-model",
        help="override the cross encoder, e.g. ms-marco-MultiBERT-L-12",
    )
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    path = HERE / args.file

    try:
        if args.command == "build":
            build(path, args.rebuild)
        else:
            if not args.query:
                parser.error(f"{args.command} needs --query")
            documents = parse_articles(path)
            if args.command == "search":
                show(args.method, args.query, documents, args.top, args.rerank_model)
            else:
                compare(args.query, documents, args.top, args.rerank_model)
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
