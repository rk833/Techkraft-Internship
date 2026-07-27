# Agentic RAG Chatbot (Local Documents Q&A)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your Gemini API key
```

## Usage
## Month 3: Agents, Safety, and Capstone

### Week 9: Agent Basics
**Topics**
- What an AI agent is
- Chatbot vs agent
- Tool use and function calling
- Planning and action loops
- When to use agents and when not to

**Practice**
- Build a small tool-using assistant
- Test simple tool calls

**Deliverable**
- Basic agent demo

**Option A — Streamlit (recommended, does upload + ingestion + chat in one place):**
```bash
streamlit run app.py
```
Upload files in the sidebar (or drop them straight into the `docs/` folder),
click "Ingest documents", then chat.

**Option B — put files in `docs/` yourself, ingest via CLI:**
```bash
mkdir -p docs   # then copy your .pdf / .docx / .txt / .md files in here
python ingest.py
streamlit run app.py
```

## How it works

- `ingest.py` — reads every supported file out of `./docs`
  (`.txt`, `.md`, `.pdf`, `.docx`), extracts plain text (page-by-page for
  PDFs, paragraph-by-paragraph for Word docs), chunks it (800 chars, 150
  overlap), embeds each chunk with Gemini's `text-embedding-004`, stores
  vectors + source filenames in a local persistent ChromaDB folder
  (`./chroma_db`).
- `tools.py` — defines `search_docs()`, which embeds a query and does a
  similarity search against that ChromaDB collection. Also defines the
  JSON schema (`FunctionDeclaration`) that tells Gemini this tool exists
  and how to call it.
- `agent.py` — the agentic loop: sends the conversation + tool to
  `gemini-2.5-flash`, and if the model responds with a function call
  instead of text, runs `search_docs()` and feeds the result back in,
  repeating until the model gives a final text answer (capped at 5 tool
  calls per question so it can't loop forever).
- `app.py` — Streamlit UI wrapping the above: sidebar to upload files into
  `docs/` and trigger ingestion, chat panel that calls `run_agent()` per
  message and keeps conversation history so follow-ups have context.

## Adding a new file type

Add an extractor function in `ingest.py` and register it in the
`EXTRACTORS` dict — everything else (chunking, embedding, storage, the
Streamlit uploader's allowed types) picks it up automatically.

## Notes / things to tune later

- Re-ingesting replaces the whole collection (simplest to reason about
  while learning). Ingestion is not incremental — every run reprocesses
  everything currently in `docs/`.
- Chunking is naive (fixed character window). A better version later:
  chunk by paragraph/heading structure so chunks don't split mid-sentence.
- PDF text extraction can be messy for scanned/image-based PDFs (no OCR
  here) — works best on text-native PDFs.
- Verify `text-embedding-004` and `gemini-2.5-flash` are still the model
  names in Gemini's current docs before running — API model names change
  over time.
