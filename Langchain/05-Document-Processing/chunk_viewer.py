"""
Module 05 mini project: Document Chunk Viewer.

Loads a PDF, DOCX or TXT file and shows exactly how LangChain splits it into
chunks, so the effect of chunk size, overlap and splitter choice is visible
rather than guessed at.

Makes no API calls. Everything here runs locally, so experiment freely.

Usage:
    python make_samples.py
    python chunk_viewer.py sample.pdf
    python chunk_viewer.py sample.pdf --chunk-size 300 --chunk-overlap 60
    python chunk_viewer.py sample.txt --splitter character
    python chunk_viewer.py sample.docx --show-overlap
    python chunk_viewer.py sample.pdf --compare
"""

import argparse
import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
    TokenTextSplitter,
)

# langchain-community is being sunset, and warns loudly on import. Only the
# loaders that have no maintained standalone replacement are taken from it. The
# warning is suppressed around the import itself, because a module level
# filterwarnings call does not catch it: the filter is matched against the
# module raising the warning, which here is this file rather than the library.
import warnings  # noqa: E402

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from langchain_community.document_loaders import PyPDFLoader, TextLoader


def load_docx(path: Path) -> list:
    """
    A hand written DOCX loader.

    LangChain's Docx2txtLoader needs the separate docx2txt package. Rather than
    add another dependency, this uses python-docx directly, which also shows
    what a loader actually is: something that returns Document objects holding
    page_content and metadata. There is nothing magic about the built in ones.
    """
    from docx import Document as DocxFile

    document = DocxFile(path)
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    return [Document(page_content=text, metadata={"source": str(path)})]


def load(path: Path) -> list:
    """Pick a loader from the file extension."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        # PyPDFLoader returns one Document per page, and records the page number
        # in metadata. That per page split happens before any chunking.
        return PyPDFLoader(str(path)).load()
    if suffix == ".docx":
        return load_docx(path)
    if suffix in (".txt", ".md"):
        return TextLoader(str(path), encoding="utf-8").load()

    raise ValueError(f"unsupported file type: {suffix}. Use .pdf, .docx, .txt or .md")


def build_splitter(kind: str, chunk_size: int, chunk_overlap: int):
    """
    The three splitters differ in where they are willing to cut.

    recursive  tries paragraph breaks, then line breaks, then spaces, then
               anywhere. Keeps related text together, so this is the default
               choice for most work.
    character  cuts on one separator only, by default a blank line. Simple, but
               a document without that separator will not split at all.
    token      counts tokens rather than characters, which is what actually
               matters for a model's context limit.
    """
    if kind == "recursive":
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
    if kind == "character":
        return CharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, separator="\n\n"
        )
    return TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def count_tokens(text: str) -> int:
    """
    Approximate token count.

    tiktoken is OpenAI's tokenizer, not Gemini's, so this is an estimate. It is
    close enough to reason about chunk sizes. An exact count needs the
    provider's own count_tokens call, which costs a request.
    """
    import tiktoken

    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def find_overlap(first: str, second: str, limit: int = 400) -> str:
    """
    The longest text that ends the first chunk and starts the second.

    Splitters do not report the overlap they produced, so it is recovered here
    by comparison. Seeing the real value is more convincing than trusting the
    chunk_overlap setting was honoured, because it often is not exactly.
    """
    longest = min(len(first), len(second), limit)
    for size in range(longest, 0, -1):
        if first[-size:] == second[:size]:
            return first[-size:]
    return ""


def preview(text: str, width: int) -> str:
    """One line preview, with newlines made visible."""
    flat = text.replace("\n", "\\n")
    if len(flat) <= width:
        return flat
    return flat[:width] + "..."


def show_chunks(chunks: list, width: int, show_overlap: bool) -> None:
    for index, chunk in enumerate(chunks):
        page = chunk.metadata.get("page_label") or chunk.metadata.get("page")
        location = f" page={page}" if page is not None else ""
        print(
            f"[{index:>3}] chars={len(chunk.page_content):<5} "
            f"tokens={count_tokens(chunk.page_content):<5}{location}"
        )
        print(f"      {preview(chunk.page_content, width)}")

        if show_overlap and index + 1 < len(chunks):
            shared = find_overlap(chunk.page_content, chunks[index + 1].page_content)
            if shared:
                print(f"      overlap with next: {len(shared)} chars: {preview(shared, width)}")
            else:
                print("      overlap with next: none")
        print()


def show_stats(documents: list, chunks: list, chunk_size: int) -> None:
    sizes = [len(c.page_content) for c in chunks]
    total = sum(sizes)
    original = sum(len(d.page_content) for d in documents)

    print("stats")
    print(f"  documents loaded:  {len(documents)}")
    print(f"  original chars:    {original}")
    print(f"  chunks produced:   {len(chunks)}")
    if not sizes:
        return
    print(f"  chunk chars:       min {min(sizes)}, avg {total // len(sizes)}, max {max(sizes)}")

    oversized = [s for s in sizes if s > chunk_size]
    if oversized:
        print(
            f"  over chunk_size:   {len(oversized)} chunk(s), largest {max(oversized)}"
        )
        print("                     a chunk can exceed the limit when no separator fits")

    duplicated = total - original
    if duplicated > 0:
        share = (duplicated / original) * 100
        print(f"  repeated by overlap: {duplicated} chars ({share:.1f}% more than the original)")


def compare(documents: list, chunk_size: int, chunk_overlap: int) -> None:
    """Same document through all three splitters, side by side."""
    print(f"chunk_size={chunk_size} chunk_overlap={chunk_overlap}")
    print()
    print(
        f"{'splitter':<12} {'chunks':>7} {'min ch':>7} {'avg ch':>7} "
        f"{'max ch':>7} {'avg tok':>8}"
    )

    for kind in ("recursive", "character", "token"):
        chunks = build_splitter(kind, chunk_size, chunk_overlap).split_documents(documents)
        sizes = [len(c.page_content) for c in chunks] or [0]
        tokens = [count_tokens(c.page_content) for c in chunks] or [0]
        print(
            f"{kind:<12} {len(chunks):>7} {min(sizes):>7} "
            f"{sum(sizes) // len(sizes):>7} {max(sizes):>7} "
            f"{sum(tokens) // len(tokens):>8}"
        )

    print()
    print("chunk_size means characters for recursive and character, but tokens for")
    print("token. A token is roughly four characters of English, so the same number")
    print("produces much larger chunks under the token splitter.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show how a document is split into chunks."
    )
    parser.add_argument("path", help="path to a .pdf, .docx, .txt or .md file")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument(
        "--splitter",
        choices=("recursive", "character", "token"),
        default="recursive",
    )
    parser.add_argument(
        "--preview-width", type=int, default=90, help="characters shown per chunk"
    )
    parser.add_argument(
        "--show-overlap",
        action="store_true",
        help="show the text shared between neighbouring chunks",
    )
    parser.add_argument(
        "--stats-only", action="store_true", help="skip the per chunk listing"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="compare all three splitters on the same document",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"file not found: {path}")
        print("run 'python make_samples.py' to create the sample documents")
        return 1

    if args.chunk_overlap >= args.chunk_size:
        print("chunk-overlap must be smaller than chunk-size")
        return 1

    try:
        documents = load(path)
    except ValueError as error:
        print(error)
        return 1

    print(f"loaded {len(documents)} document(s) from {path.name}")
    print(f"metadata of first: {documents[0].metadata}")
    print()

    if args.compare:
        compare(documents, args.chunk_size, args.chunk_overlap)
        return 0

    splitter = build_splitter(args.splitter, args.chunk_size, args.chunk_overlap)
    chunks = splitter.split_documents(documents)

    print(
        f"splitter={args.splitter} chunk_size={args.chunk_size} "
        f"chunk_overlap={args.chunk_overlap}"
    )
    print()

    if not args.stats_only:
        show_chunks(chunks, args.preview_width, args.show_overlap)

    show_stats(documents, chunks, args.chunk_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
