"""
Module 08 mini project: Chat with One PDF.

The full Retrieval-Augmented Generation loop, built from the pieces of the
earlier modules:

    load and chunk the PDF        Module 05
    embed the chunks             Module 06
    store them                   Module 07
    retrieve, then answer        this module

    build   index the PDF once
    ask     answer a question using retrieved context
    show    retrieve only, print the chunks, call no chat model

The prompt is the part worth studying. A retriever always returns k chunks
whether or not any of them are relevant, so the instruction that the model may
answer only from those chunks, and must otherwise say it does not know, is what
stops the whole thing inventing answers.

Usage:
    python make_sample.py
    python rag_chat.py build
    python rag_chat.py ask --question "how many days of annual leave do I get"
    python rag_chat.py ask --question "..." --show-context
    python rag_chat.py ask --question "..." --no-grounding
    python rag_chat.py show --question "..."
"""

import argparse
import shutil
import sys
import warnings
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import ConfigError, active_embedding_model, describe_api_error, run_with_fallback
from common.embeddings import build_embeddings
from common.models import active_model_name, api_keys

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from langchain_community.document_loaders import PyPDFLoader

HERE = Path(__file__).resolve().parent
STORE_DIR = HERE / "chroma_db"
COLLECTION = "handbook"

# Grounded: the model is told what it may use and what to do when the context
# does not cover the question. Every line here earns its place.
GROUNDED_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions about a staff handbook.\n"
            "Use ONLY the context below. Do not use general knowledge, and do "
            "not guess.\n"
            "If the context does not contain the answer, reply exactly: "
            "I don't know based on the handbook.\n"
            "Quote specific numbers and limits exactly as written.\n"
            "Cite the page number for each fact, like (page 2).\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ]
)

# Ungrounded: the same context, with the guard rails removed. Used by
# --no-grounding to show what those instructions were doing.
UNGROUNDED_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions about a staff handbook.\n\n"
            "Context:\n{context}",
        ),
        ("human", "{question}"),
    ]
)


def embeddings_for(task_type: str):
    """The store calls the embedding model itself, so it needs the object."""
    return build_embeddings(active_embedding_model(), api_keys()[0], task_type=task_type)


def build(pdf: Path, chunk_size: int, chunk_overlap: int, rebuild: bool) -> None:
    if not pdf.exists():
        raise ConfigError(
            f"{pdf.name} not found. run 'python make_sample.py' first"
        )

    pages = PyPDFLoader(str(pdf)).load()
    print(f"loaded {len(pages)} pages from {pdf.name}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = splitter.split_documents(pages)
    print(f"split into {len(chunks)} chunks of up to {chunk_size} characters")

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
    print()
    print("one batched request embedded every chunk. asking a question costs")
    print("two calls: one to embed the question, one to answer it.")


def open_store() -> Chroma:
    if not STORE_DIR.exists():
        raise ConfigError("no index found. run 'python rag_chat.py build' first")
    return Chroma(
        collection_name=COLLECTION,
        persist_directory=str(STORE_DIR),
        embedding_function=embeddings_for("RETRIEVAL_QUERY"),
    )


def format_context(documents: list) -> str:
    """
    Turn retrieved chunks into the text the model reads.

    The page number is included in the text itself, not just in metadata,
    because the model cannot see metadata. Without this it has no way to cite
    anything, and asking it to cite pages would invite invented numbers.
    """
    blocks = []
    for document in documents:
        page = document.metadata.get("page_label", "?")
        blocks.append(f"[page {page}]\n{document.page_content}")
    return "\n\n".join(blocks)


def build_chain(model, prompt, retriever):
    """
    The RAG chain.

    The retriever is just another runnable, so it composes with the pieces from
    Module 04. .assign runs retrieval and adds the result under context, while
    keeping the original question for the prompt.
    """
    return (
        RunnablePassthrough.assign(
            context=(lambda inputs: inputs["question"]) | retriever | RunnableLambda(format_context)
        )
        | prompt
        | model
        | StrOutputParser()
    )


def show(question: str, top: int) -> None:
    """Retrieval only. No chat model is called, so this costs one embed call."""
    retriever = open_store().as_retriever(search_kwargs={"k": top})
    documents = retriever.invoke(question)

    print(f"question: {question}")
    print(f"retrieved {len(documents)} chunks")
    print()
    for index, document in enumerate(documents):
        page = document.metadata.get("page_label", "?")
        text = document.page_content.replace("\n", " ")
        print(f"[{index}] page {page}")
        print(f"    {text[:300]}{'...' if len(text) > 300 else ''}")
        print()
    print("this is exactly what the model will be given as context.")


def ask(question: str, top: int, show_context: bool, grounded: bool) -> None:
    store = open_store()
    retriever = store.as_retriever(search_kwargs={"k": top})

    if show_context:
        documents = retriever.invoke(question)
        print("context passed to the model:")
        print(format_context(documents))
        print()
        print("-" * 60)
        print()

    prompt = GROUNDED_PROMPT if grounded else UNGROUNDED_PROMPT
    if not grounded:
        print("[grounding instructions removed]")
        print()

    answer = run_with_fallback(
        lambda model: build_chain(model, prompt, retriever).invoke(
            {"question": question}
        ),
        temperature=0.0,
    )

    print(f"question: {question}")
    print()
    print(answer.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer questions about a PDF.")
    parser.add_argument("command", choices=("build", "ask", "show"))
    parser.add_argument("--question", help="what to ask")
    parser.add_argument("--file", default="handbook.pdf", help="PDF to index")
    parser.add_argument("--top", type=int, default=4, help="chunks to retrieve")
    parser.add_argument("--chunk-size", type=int, default=600)
    parser.add_argument("--chunk-overlap", type=int, default=120)
    parser.add_argument(
        "--show-context", action="store_true", help="print the retrieved chunks too"
    )
    parser.add_argument(
        "--no-grounding",
        action="store_true",
        help="drop the answer-only-from-context instructions, to see their effect",
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="delete the existing index first"
    )
    parser.add_argument("--debug", action="store_true", help="show the full traceback")
    args = parser.parse_args()

    try:
        if args.command == "build":
            build(HERE / args.file, args.chunk_size, args.chunk_overlap, args.rebuild)
        else:
            if not args.question:
                parser.error(f"{args.command} needs --question")
            if args.command == "show":
                show(args.question, args.top)
            else:
                ask(args.question, args.top, args.show_context, not args.no_grounding)
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
