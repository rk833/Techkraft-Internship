"""
ingest.py
Reads every supported document out of a local ./docs folder, extracts
text, chunks it, embeds each chunk with Gemini's embedding model, and
stores everything in a local persistent ChromaDB collection.

Supported file types: .txt, .md, .pdf, .docx

Usage:
    1. Drop files into ./docs  (create it if it doesn't exist)
    2. python ingest.py

Or import `ingest_docs_folder()` from app.py (Streamlit sidebar button).
"""

import os
import glob

import chromadb
from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader
from docx import Document as DocxDocument

load_dotenv()

DOCS_DIR = "./docs"
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "my_docs"
EMBED_MODEL = "models/gemini-embedding-001"   # Gemini's embedding model
CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 150     # overlap so context isn't cut mid-thought

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)


# ---------- text extraction per file type ----------

def extract_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def extract_docx(path: str) -> str:
    doc = DocxDocument(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


EXTRACTORS = {
    ".txt": extract_txt,
    ".md": extract_txt,
    ".pdf": extract_pdf,
    ".docx": extract_docx,
}


def load_documents(docs_dir: str = DOCS_DIR) -> list[tuple[str, str]]:
    """Returns list of (filename, extracted_text) for every supported file."""
    docs = []
    for path in glob.glob(os.path.join(docs_dir, "*")):
        ext = os.path.splitext(path)[1].lower()
        extractor = EXTRACTORS.get(ext)
        if not extractor:
            continue  # skip unsupported file types silently
        try:
            text = extractor(path)
        except Exception as e:
            print(f"Skipping {path}: {e}")
            continue
        if text.strip():
            docs.append((os.path.basename(path), text))
    return docs


# ---------- chunking (unchanged logic from before) ----------

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple sliding-window character chunking."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return [c for c in chunks if len(c.strip()) > 50]  # drop tiny scraps


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed a list of strings via Gemini's embedding API."""
    result = client.models.embed_content(model=EMBED_MODEL, contents=texts)
    return [e.values for e in result.embeddings]


# ---------- main ingestion ----------

def ingest_docs_folder(docs_dir: str = DOCS_DIR) -> int:
    """
    Reads all supported files in docs_dir, chunks + embeds everything,
    and (re)builds the ChromaDB collection.
    Returns the number of chunks stored.
    """
    documents = load_documents(docs_dir)
    if not documents:
        raise ValueError(
            f"No supported documents found in '{docs_dir}'. "
            f"Supported types: {', '.join(EXTRACTORS)}"
        )

    # fresh collection each ingest so re-running doesn't duplicate data
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = chroma_client.create_collection(COLLECTION_NAME)

    all_chunks, all_metas = [], []
    for filename, text in documents:
        chunks = chunk_text(text)
        for c in chunks:
            all_chunks.append(c)
            all_metas.append({"source": filename})

    if not all_chunks:
        raise ValueError("Documents were found but produced no usable text chunks.")

    # embed + store in batches (API limits on how many texts per call)
    batch_size = 20
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        metas = all_metas[i:i + batch_size]
        embeddings = embed_texts(batch)
        ids = [f"chunk_{i+j}" for j in range(len(batch))]
        collection.add(documents=batch, embeddings=embeddings, metadatas=metas, ids=ids)

    return len(all_chunks)


if __name__ == "__main__":
    n = ingest_docs_folder()
    print(f"Ingested {n} chunks from files in '{DOCS_DIR}' into '{CHROMA_DIR}'.")
