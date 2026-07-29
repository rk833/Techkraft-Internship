"""
Module 07 mini project: Personal Notes Search.

Stores notes in a vector database and retrieves them by meaning, showing what a
vector store adds over the raw embeddings of Module 06: persistence, metadata
filtering, and a query interface.

    build    embed the notes once and write them to disk
    search   query the stored notes, optionally filtered by category
    compare  run the same query through Chroma and FAISS
    stats    what is currently stored, no API call

Building embeds every note in one batched request. After that each search costs
a single call to embed the query, because the notes are already stored. That
split is the main practical reason to use a vector database.

Usage:
    python notes_search.py build
    python notes_search.py search --query "why was the service slow"
    python notes_search.py search --query "appointment" --category personal
    python notes_search.py compare --query "how big should chunks be"
    python notes_search.py stats
"""

import argparse
import shutil
import sys
import warnings
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_embedding_model, describe_api_error
from common.embeddings import build_embeddings
from common.models import api_keys

# FAISS still lives in langchain-community, which warns that it is being sunset.
# Chroma has a maintained standalone package, langchain-chroma, and is used as
# the default here for that reason.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from langchain_community.vectorstores import FAISS

HERE = Path(__file__).resolve().parent
CHROMA_DIR = HERE / "chroma_db"
FAISS_DIR = HERE / "faiss_index"
COLLECTION = "notes"


def embeddings_for(task_type: str):
    """
    An embedding model for the store to call itself.

    The vector store calls embed_documents and embed_query on its own, so it
    needs the model rather than a finished vector. That rules out the
    embed_with_fallback wrapper used in Module 06, so the first key and model
    are used directly.
    """
    return build_embeddings(active_embedding_model(), api_keys()[0], task_type=task_type)


def parse_notes(path: Path) -> list:
    """
    Read the notes file into Documents.

    Metadata is attached here, at load time. It has to exist before the note is
    stored, because filtering happens inside the database and cannot be added
    afterwards without rebuilding.
    """
    if not path.exists():
        raise ConfigError(f"notes file not found: {path}")

    documents = []
    category = title = None
    body = []

    def flush():
        if category and body:
            text = " ".join(body).strip()
            documents.append(
                Document(
                    page_content=f"{title}\n{text}",
                    metadata={"category": category, "title": title},
                )
            )

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("[") and "]" in stripped:
            flush()
            category = stripped[1 : stripped.index("]")]
            title = stripped[stripped.index("]") + 1 :].strip()
            body = []
        elif stripped:
            body.append(stripped)

    flush()

    if not documents:
        raise ConfigError(f"no notes found in {path}")
    return documents


def build(path: Path, rebuild: bool) -> None:
    documents = parse_notes(path)
    print(f"parsed {len(documents)} notes from {path.name}")

    if rebuild:
        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
        shutil.rmtree(FAISS_DIR, ignore_errors=True)
        print("removed existing stores")

    # RETRIEVAL_DOCUMENT because these are passages that will be searched, not
    # queries. Module 06 covers why the pair matters.
    embeddings = embeddings_for("RETRIEVAL_DOCUMENT")

    # hnsw:space=cosine makes the returned score a cosine distance, so
    # similarity is 1 - score. The default, l2, returns squared euclidean
    # distance instead, which is harder to read.
    store = Chroma.from_documents(
        documents,
        embeddings,
        collection_name=COLLECTION,
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )
    print(f"chroma:  wrote {store._collection.count()} vectors to {CHROMA_DIR.name}/")

    faiss_store = FAISS.from_documents(documents, embeddings)
    faiss_store.save_local(str(FAISS_DIR))
    print(f"faiss:   wrote {faiss_store.index.ntotal} vectors to {FAISS_DIR.name}/")

    print()
    print("one batched request embedded every note. searches from now on only")
    print("embed the query, so they cost one call each.")


def open_chroma() -> Chroma:
    if not CHROMA_DIR.exists():
        raise ConfigError("no store found. run 'python notes_search.py build' first")
    return Chroma(
        collection_name=COLLECTION,
        persist_directory=str(CHROMA_DIR),
        embedding_function=embeddings_for("RETRIEVAL_QUERY"),
    )


def open_faiss() -> FAISS:
    if not FAISS_DIR.exists():
        raise ConfigError("no store found. run 'python notes_search.py build' first")
    # allow_dangerous_deserialization is required because a FAISS store is
    # loaded with pickle, which can execute code. Safe for a file this script
    # wrote, not safe for one downloaded from anywhere.
    return FAISS.load_local(
        str(FAISS_DIR),
        embeddings_for("RETRIEVAL_QUERY"),
        allow_dangerous_deserialization=True,
    )


def show_hits(hits: list, note: str) -> None:
    print(f"{'score':>8}  {'similarity':>10}  category   title")
    for document, score in hits:
        # cosine distance, so similarity is 1 - score
        print(
            f"{score:>8.4f}  {1 - score:>10.4f}  "
            f"{document.metadata['category']:<9}  {document.metadata['title']}"
        )
    print()
    print(note)


def search(query: str, category: str, top: int) -> None:
    store = open_chroma()

    # the filter is applied inside the database, so it narrows the candidates
    # before ranking rather than discarding results afterwards
    where = {"category": category} if category else None
    hits = store.similarity_search_with_score(query, k=top, filter=where)

    print(f"query:    {query}")
    if category:
        print(f"filter:   category = {category}")
    print()

    if not hits:
        print("no matches")
        return

    show_hits(
        hits,
        "score is a cosine DISTANCE, so lower is better. sorting by it descending\n"
        "would give you the worst matches first.",
    )


def compare(query: str, top: int) -> None:
    """
    Same query through both stores.

    The scores differ because the two use different distance measures by
    default, not because one is finding better matches.
    """
    print(f"query: {query}")
    print()

    chroma_hits = open_chroma().similarity_search_with_score(query, k=top)
    print("chroma (cosine distance, lower is better)")
    for document, score in chroma_hits:
        print(f"  {score:>8.4f}  {document.metadata['title']}")

    faiss_hits = open_faiss().similarity_search_with_score(query, k=top)
    print()
    print("faiss (squared euclidean distance, lower is better)")
    for document, score in faiss_hits:
        print(f"  {score:>8.4f}  {document.metadata['title']}")

    print()
    same = [c.metadata["title"] for c, _ in chroma_hits] == [
        f.metadata["title"] for f, _ in faiss_hits
    ]
    print(f"same ranking: {same}")
    print()
    print("for unit length vectors the two measures are related by")
    print("  squared euclidean = 2 x cosine distance")
    print("so the ordering agrees even though the numbers do not.")


def stats() -> None:
    """What is stored, without embedding anything."""
    if not CHROMA_DIR.exists():
        print("no store found. run 'python notes_search.py build' first")
        return

    store = open_chroma()
    data = store.get(include=["metadatas"])
    metadatas = data["metadatas"]

    print(f"collection: {COLLECTION}")
    print(f"vectors:    {len(metadatas)}")
    print(f"on disk:    {CHROMA_DIR.name}/")
    print()

    counts = {}
    for meta in metadatas:
        counts[meta["category"]] = counts.get(meta["category"], 0) + 1

    print("by category")
    for name in sorted(counts):
        print(f"  {name:<10} {counts[name]}")

    print()
    print("no API call was made. metadata is stored alongside the vectors.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Search personal notes by meaning.")
    parser.add_argument(
        "command", choices=("build", "search", "compare", "stats")
    )
    parser.add_argument("--query", help="what to search for")
    parser.add_argument("--category", help="restrict to one category")
    parser.add_argument("--file", default="sample_notes.txt", help="notes file")
    parser.add_argument("--top", type=int, default=4, help="results to show")
    parser.add_argument(
        "--rebuild", action="store_true", help="delete existing stores first"
    )
    parser.add_argument("--debug", action="store_true", help="show the full traceback")
    args = parser.parse_args()

    try:
        if args.command == "build":
            build(HERE / args.file, args.rebuild)
        elif args.command == "stats":
            stats()
        else:
            if not args.query:
                parser.error(f"{args.command} needs --query")
            if args.command == "search":
                search(args.query, args.category, args.top)
            else:
                compare(args.query, args.top)
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
