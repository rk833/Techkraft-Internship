"""
Module 09 mini project: Multi-PDF Research Assistant.

Searches across three documents owned by different departments, and compares
four retrieval strategies against the plain vector search from Module 08.

    basic        similarity search, the Module 08 baseline
    multiquery   an LLM rewrites the question several ways, results are merged
    parent       search small chunks, return the larger section around them
    compression  retrieve widely, then drop chunks that do not clear a bar
    selfquery    an LLM splits the question into a search term and a filter

Retrieval is the expensive part to get right, so every strategy can be run with
`show`, which retrieves and prints without calling a chat model to answer.

    build    index the PDFs
    show     retrieve only, print what came back
    ask      retrieve and answer
    compare  run several retrievers on one question, retrieval only

Usage:
    python make_samples.py
    python research_assistant.py build
    python research_assistant.py show --question "..." --retriever multiquery
    python research_assistant.py compare --question "..."
    python research_assistant.py ask --question "..." --retriever parent
"""

import argparse
import shutil
import sys
import warnings
from pathlib import Path

from langchain_chroma import Chroma
from langchain_classic.retrievers import (
    ContextualCompressionRetriever,
    ParentDocumentRetriever,
)
from langchain_classic.retrievers.document_compressors import EmbeddingsFilter
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_classic.retrievers.self_query.base import SelfQueryRetriever
from langchain_classic.storage import InMemoryStore

# AttributeInfo describes a metadata field to SelfQueryRetriever. In LangChain
# 1.x it lives here, not in langchain_core.structured_query, which holds the
# filter expression types instead.
from langchain_classic.chains.query_constructor.schema import AttributeInfo
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_embedding_model, describe_api_error, run_with_fallback
from common.embeddings import build_embeddings
from common.models import active_model_name, api_keys, build_model

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from langchain_community.document_loaders import PyPDFLoader

HERE = Path(__file__).resolve().parent
STORE_DIR = HERE / "chroma_db"
COLLECTION = "research"

# Department and year are attached at load time so SelfQueryRetriever has
# something to filter on. Descriptions are written for the model to read.
METADATA_FIELDS = [
    AttributeInfo(
        name="department",
        description="Which team owns the document. One of: people, security, engineering.",
        type="string",
    ),
    AttributeInfo(
        name="year",
        description="Year the document was published, either 2025 or 2026.",
        type="integer",
    ),
]

ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions using company documents.\n"
            "Use ONLY the context below. Do not guess.\n"
            "If the context does not contain the answer, reply exactly: "
            "I don't know based on these documents.\n"
            "When two documents disagree or overlap, say so explicitly.\n"
            "Cite the document name and page for each fact, like "
            "(security-policy.pdf page 2).\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ]
)

DOCUMENT_META = {
    "people-handbook.pdf": {"department": "people", "year": 2025},
    "security-policy.pdf": {"department": "security", "year": 2026},
    "engineering-guide.pdf": {"department": "engineering", "year": 2026},
}


def embeddings_for(task_type: str):
    return build_embeddings(active_embedding_model(), api_keys()[0], task_type=task_type)


def load_documents() -> list:
    """Load every PDF and attach its department and year."""
    documents = []
    for name, meta in DOCUMENT_META.items():
        path = HERE / name
        if not path.exists():
            raise ConfigError(
                f"{name} not found. run 'python make_samples.py' first"
            )
        for page in PyPDFLoader(str(path)).load():
            page.metadata.update(meta)
            page.metadata["document"] = name
            documents.append(page)
    return documents


def build(chunk_size: int, chunk_overlap: int, rebuild: bool) -> None:
    documents = load_documents()
    print(f"loaded {len(documents)} pages from {len(DOCUMENT_META)} documents")

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    ).split_documents(documents)
    print(f"split into {len(chunks)} chunks")

    if rebuild:
        shutil.rmtree(STORE_DIR, ignore_errors=True)

    store = Chroma.from_documents(
        chunks,
        embeddings_for("RETRIEVAL_DOCUMENT"),
        collection_name=COLLECTION,
        persist_directory=str(STORE_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )
    print(f"stored {store._collection.count()} vectors in {STORE_DIR.name}/")


def open_store() -> Chroma:
    if not STORE_DIR.exists():
        raise ConfigError("no index found. run 'python research_assistant.py build' first")
    return Chroma(
        collection_name=COLLECTION,
        persist_directory=str(STORE_DIR),
        embedding_function=embeddings_for("RETRIEVAL_QUERY"),
    )


def make_retriever(kind: str, top: int, verbose: bool = False):
    """
    Build one retriever.

    Each wraps or replaces the plain similarity search in a different way, and
    each has a different cost. The chat model is only constructed for the kinds
    that actually need one.
    """
    store = open_store()
    base = store.as_retriever(search_kwargs={"k": top})

    if kind == "basic":
        return base

    if kind == "multiquery":
        # one LLM call rewrites the question several ways, then each rewrite is
        # searched and the results are merged and deduplicated
        return MultiQueryRetriever.from_llm(
            retriever=base,
            llm=build_model(active_model_name(), api_keys()[0], temperature=0.0),
        )

    if kind == "compression":
        # EmbeddingsFilter drops retrieved chunks below a similarity threshold.
        # It uses embeddings rather than an LLM, so it is cheap. LLMChainExtractor
        # is the alternative and costs one LLM call per retrieved chunk.
        return ContextualCompressionRetriever(
            base_compressor=EmbeddingsFilter(
                embeddings=embeddings_for("RETRIEVAL_QUERY"),
                similarity_threshold=0.55,
            ),
            base_retriever=store.as_retriever(search_kwargs={"k": top * 2}),
        )

    if kind == "selfquery":
        # one LLM call turns "what does the security policy say about passwords"
        # into a search for "passwords" plus a filter of department = security
        #
        # structured_query_translator is passed explicitly. Left to itself,
        # from_llm inspects the store to pick a translator, and that lookup
        # imports every supported vector store, which fails on this combination
        # of langchain-classic and langchain-community versions.
        from langchain_community.query_constructors.chroma import ChromaTranslator

        return SelfQueryRetriever.from_llm(
            build_model(active_model_name(), api_keys()[0], temperature=0.0),
            store,
            "Company policy documents covering HR, security and engineering.",
            METADATA_FIELDS,
            structured_query_translator=ChromaTranslator(),
            search_kwargs={"k": top},
            verbose=verbose,
        )

    return make_parent_retriever(top)


def make_parent_retriever(top: int):
    """
    ParentDocumentRetriever indexes small chunks but returns their larger parent.

    Small chunks match precisely; large chunks carry enough context to answer
    from. This gets both, at the cost of holding the parents in a second store.

    The parent store here is in memory, so it is rebuilt on every run. That
    re-embeds the documents each time, which is why this retriever is more
    expensive than it looks. A real system would persist it.
    """
    child_store = Chroma(
        collection_name="parent_children",
        embedding_function=embeddings_for("RETRIEVAL_DOCUMENT"),
        collection_metadata={"hnsw:space": "cosine"},
    )
    retriever = ParentDocumentRetriever(
        vectorstore=child_store,
        docstore=InMemoryStore(),
        child_splitter=RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40),
        parent_splitter=RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=0),
        search_kwargs={"k": top},
    )
    retriever.add_documents(load_documents())
    return retriever


def format_context(documents: list) -> str:
    """Document name and page go into the text, since metadata is not sent."""
    blocks = []
    for document in documents:
        name = document.metadata.get("document", "?")
        page = document.metadata.get("page_label", "?")
        blocks.append(f"[{name} page {page}]\n{document.page_content}")
    return "\n\n".join(blocks)


def print_documents(documents: list, width: int = 220) -> None:
    if not documents:
        print("  nothing retrieved")
        return
    for index, document in enumerate(documents):
        name = document.metadata.get("document", "?")
        page = document.metadata.get("page_label", "?")
        text = document.page_content.replace("\n", " ")
        print(f"  [{index}] {name} page {page}  ({len(document.page_content)} chars)")
        print(f"      {text[:width]}{'...' if len(text) > width else ''}")


def show(question: str, kind: str, top: int, verbose: bool) -> None:
    retriever = make_retriever(kind, top, verbose)
    documents = retriever.invoke(question)

    print(f"question:  {question}")
    print(f"retriever: {kind}")
    print(f"retrieved: {len(documents)} chunks")
    print()
    print_documents(documents)

    sources = sorted({d.metadata.get("document", "?") for d in documents})
    print()
    print(f"documents covered: {', '.join(sources)}")


def compare(question: str, kinds: list, top: int) -> None:
    """Retrieval only, across several strategies. No answers generated."""
    print(f"question: {question}")
    print()

    for kind in kinds:
        print(f"--- {kind} ---")
        try:
            documents = retriever_documents(kind, question, top)
        except Exception as error:
            print(f"  failed: {type(error).__name__}: {str(error)[:120]}")
            print()
            continue

        sources = sorted({d.metadata.get("document", "?") for d in documents})
        sizes = [len(d.page_content) for d in documents] or [0]
        print(
            f"  {len(documents)} chunks, {len(sources)} document(s), "
            f"avg {sum(sizes) // len(sizes)} chars"
        )
        for name in sources:
            count = sum(1 for d in documents if d.metadata.get("document") == name)
            print(f"    {name}: {count}")
        print()


def retriever_documents(kind: str, question: str, top: int) -> list:
    return make_retriever(kind, top).invoke(question)


def ask(question: str, kind: str, top: int, show_context: bool) -> None:
    retriever = make_retriever(kind, top)

    if show_context:
        documents = retriever.invoke(question)
        print("context:")
        print(format_context(documents))
        print()
        print("-" * 60)
        print()

    chain = (
        RunnablePassthrough.assign(
            context=(lambda inputs: inputs["question"])
            | retriever
            | RunnableLambda(format_context)
        )
        | ANSWER_PROMPT
        | RunnableLambda(lambda prompt: prompt)
    )

    answer = run_with_fallback(
        lambda model: (chain | model | StrOutputParser()).invoke({"question": question}),
        temperature=0.0,
    )

    print(f"question:  {question}")
    print(f"retriever: {kind}")
    print()
    print(answer.strip())


RETRIEVERS = ("basic", "multiquery", "parent", "compression", "selfquery")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare retrieval strategies across several PDFs."
    )
    parser.add_argument("command", choices=("build", "show", "ask", "compare"))
    parser.add_argument("--question", help="what to ask")
    parser.add_argument("--retriever", choices=RETRIEVERS, default="basic")
    parser.add_argument(
        "--retrievers",
        default="basic,multiquery,compression",
        help="comma separated list for compare",
    )
    parser.add_argument("--top", type=int, default=4)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    parser.add_argument("--show-context", action="store_true")
    parser.add_argument(
        "--verbose", action="store_true", help="show the retriever's own logging"
    )
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        import logging

        logging.basicConfig()
        logging.getLogger("langchain_classic.retrievers.multi_query").setLevel(
            logging.INFO
        )

    try:
        if args.command == "build":
            build(args.chunk_size, args.chunk_overlap, args.rebuild)
        else:
            if not args.question:
                parser.error(f"{args.command} needs --question")
            if args.command == "show":
                show(args.question, args.retriever, args.top, args.verbose)
            elif args.command == "compare":
                kinds = [k.strip() for k in args.retrievers.split(",") if k.strip()]
                compare(args.question, kinds, args.top)
            else:
                ask(args.question, args.retriever, args.top, args.show_context)
    except ConfigError as error:
        print(error)
        return 1
    except Exception as error:
        if args.debug:
            raise
        print(describe_api_error(error, active_model_name()))
        print()
        print("run again with --debug to see the full traceback")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
