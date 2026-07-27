"""
tools.py
Defines the ONE tool our agent gets: search_docs.
It queries the ChromaDB collection built by ingest.py and returns the
most relevant chunks + their source URLs.

This is the key piece that makes the system "agentic" rather than plain
RAG: the LLM decides when to call this, what query text to use, and
whether to call it again with a refined query.
"""

import chromadb
from google import genai
from google.genai import types
import os

CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "my_docs"
EMBED_MODEL = "models/gemini-embedding-001"

_chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
_genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def search_docs(query: str, n_results: int = 4) -> str:
    """
    Semantic search over the ingested website content.

    Args:
        query: the search query (can be a rephrased/refined version of
               the user's question — that's the agent's job)
        n_results: how many chunks to retrieve

    Returns:
        A formatted string of the top matching chunks with their source
        URLs, or a message saying nothing was found.
    """
    try:
        collection = _chroma_client.get_collection(COLLECTION_NAME)
    except Exception:
        return "No documents have been ingested yet. Add files to ./docs and run ingest.py first."

    query_embedding = _genai_client.models.embed_content(
        model=EMBED_MODEL, contents=[query]
    ).embeddings[0].values

    results = collection.query(query_embeddings=[query_embedding], n_results=n_results)

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        return "No relevant results found for that query."

    formatted = []
    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown")
        formatted.append(f"[Source: {source}]\n{doc}")

    return "\n\n---\n\n".join(formatted)


# --- Tool schema Gemini needs to know how/when to call search_docs ---
# This is what actually gets sent to the model alongside your messages.
search_docs_declaration = types.FunctionDeclaration(
    name="search_docs",
    description=(
        "Search the ingested documents for information relevant to a "
        "query. Use this whenever you need facts from the documents to "
        "answer the user. You can call it multiple times with "
        "different/refined queries if the first results aren't sufficient."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The search query — rephrase the user's question into good search terms.",
            ),
        },
        required=["query"],
    ),
)

rag_tool = types.Tool(function_declarations=[search_docs_declaration])
