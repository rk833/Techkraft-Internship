"""
app.py
Streamlit UI: sidebar to upload documents into ./docs and ingest them,
main panel to chat with the agentic RAG bot.

Run with:
    streamlit run app.py
"""

import os
import streamlit as st

from ingest import ingest_docs_folder, DOCS_DIR, EXTRACTORS
from agent import run_agent

st.set_page_config(page_title="Agentic RAG Chatbot", page_icon="🔎")
st.title("🔎 Agentic RAG Chatbot")
st.caption("Ask questions about the documents you've ingested. The agent decides when and how to search.")

os.makedirs(DOCS_DIR, exist_ok=True)

# ---- Session state ----
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []       # google.genai Content objects (for the model)
if "display_history" not in st.session_state:
    st.session_state.display_history = []    # (role, text) tuples (for rendering)
if "ingested" not in st.session_state:
    st.session_state.ingested = False

# ---- Sidebar: document upload + ingestion ----
with st.sidebar:
    st.header("1. Add documents")
    st.caption(f"Supported: {', '.join(EXTRACTORS)}")

    uploaded = st.file_uploader(
        "Upload files (or just drop them into the ./docs folder manually)",
        type=[ext.lstrip(".") for ext in EXTRACTORS],
        accept_multiple_files=True,
    )
    if uploaded:
        for f in uploaded:
            with open(os.path.join(DOCS_DIR, f.name), "wb") as out:
                out.write(f.getbuffer())
        st.success(f"Saved {len(uploaded)} file(s) to {DOCS_DIR}/")

    current_files = [f for f in os.listdir(DOCS_DIR) if os.path.splitext(f)[1].lower() in EXTRACTORS]
    if current_files:
        st.write("Files in ./docs:")
        st.write("\n".join(f"- {f}" for f in current_files))

    st.header("2. Ingest")
    if st.button("Ingest documents", type="primary", disabled=not current_files):
        with st.spinner("Reading, chunking, and embedding documents..."):
            try:
                n_chunks = ingest_docs_folder()
                st.session_state.ingested = True
                st.success(f"Ingested {n_chunks} chunks. You can chat now.")
            except Exception as e:
                st.error(f"Ingestion failed: {e}")

    if st.session_state.ingested:
        st.info("Documents are ready to query.")

    if st.button("Clear chat"):
        st.session_state.chat_history = []
        st.session_state.display_history = []
        st.rerun()

# ---- Main: chat ----
for role, text in st.session_state.display_history:
    with st.chat_message(role):
        st.markdown(text)

user_input = st.chat_input("Ask a question about the ingested documents...")

if user_input:
    if not st.session_state.ingested:
        st.warning("Ingest your documents first (sidebar) before asking questions.")
    else:
        st.session_state.display_history.append(("user", user_input))
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking (may search the docs a few times)..."):
                answer, updated_history = run_agent(user_input, st.session_state.chat_history)
                st.session_state.chat_history = updated_history
            st.markdown(answer)

        st.session_state.display_history.append(("assistant", answer))
