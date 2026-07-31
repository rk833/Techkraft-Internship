# LangChain Learning Guide

**Repository:** Techkraft-Internship
**Module:** LangChain Learning Journey
**Author:** Ridesha Khadka

---

## About

LangChain is one of the most widely used frameworks for building applications
powered by Large Language Models. The internship syllabus introduced LLMs,
embeddings, Retrieval-Augmented Generation and AI agents, but did not cover
LangChain specifically.

This module is a parallel hands-on learning journey. Instead of one large
application it is a series of focused mini projects, each demonstrating one
LangChain concept, so that every component is understood on its own before
being combined.

## Learning objectives

- Understand LangChain fundamentals
- Learn prompt engineering using LangChain
- Process different document types
- Work with embeddings and vector databases
- Build Retrieval-Augmented Generation pipelines
- Create AI agents capable of tool use
- Learn LangGraph workflows
- Explore Model Context Protocol
- Build production-ready AI APIs
- Understand evaluation and debugging of AI systems

## Setup

Environment setup, API keys, model selection and troubleshooting are documented
in [README.md](README.md). Do that first.

Two constraints shape how this course is worked through, and both are covered
in detail there:

- **The Gemini free tier allows 20 requests per day, per model, per project.**
  The shared helper rotates through fallback models and keys automatically when
  one runs out. Even so, prefer the offline flags (`--show-prompt`) while
  iterating, and spend live calls only once something looks right.
- **LangChain 1.x is not 0.x.** Most tutorials online target 0.x. Import paths
  and several APIs differ.

## Learning roadmap

```
Models
    v
Prompt Templates
    v
Output Parsers
    v
Chains
    v
Document Processing
    v
Embeddings
    v
Vector Databases
    v
Basic RAG
    v
Advanced RAG
    v
Retrieval Optimization
    v
Agents
    v
Memory
    v
LangGraph
    v
MCP
    v
Production AI
```

## Folder structure

```
Langchain/
    guide.md                  this file
    README.md                 setup, model choice, troubleshooting
    requirements.txt          pinned dependencies
    .env.example              template for .env
    .env                      your keys and model settings, never committed
    venv/                     shared virtual environment for all modules

    common/                   shared boilerplate only
        errors.py             error classification and messages
        models.py             chat model construction and quota fallback
        embeddings.py         embedding model construction and quota fallback

    01-Models/
    02-Prompt-Templates/
    03-Output-Parsers/
    04-Chains/
    05-Document-Processing/
    06-Embeddings/
    07-Vector-Databases/
    08-Basic-RAG/
    09-Advanced-RAG/
    10-Retrieval-Optimization/
    11-Agents/
    12-Memory/
    13-LangGraph/
    14-MCP/
    15-Production-AI/
```

`common/` holds only boilerplate: error handling and the quota fallback logic.
Anything that is part of a module's lesson stays in that module's own file, so
each project can still be read end to end on its own.

---

# Learning modules

## Module 01 - Models

**Topics:** chat models, LLMs, temperature, max tokens, streaming, structured
output.

**Mini project: AI Joke Generator.** Generate jokes from a user-provided topic.

**Concepts practised:** calling chat models, adjusting temperature, handling
responses.

## Module 02 - Prompt Templates

**Topics:** PromptTemplate, ChatPromptTemplate, variables, few-shot prompting.

**Mini project: LinkedIn Headline Generator.** Generate professional headlines
from a person's skills and career goals.

**Concepts practised:** dynamic prompts, prompt variables, message roles.

## Module 03 - Output Parsers

**Topics:** StrOutputParser, JsonOutputParser, PydanticOutputParser.

**Mini project: Movie Review Analyzer.** Convert free-text reviews into
structured data.

```json
{
    "sentiment": "Positive",
    "rating": 9
}
```

**Concepts practised:** structured output, JSON parsing, schema generated
format instructions.

## Module 04 - Chains

**Topics:** RunnableSequence, RunnableLambda, LCEL.

**Mini project: Story Generator.**

```
Topic -> Title -> Story -> Summary
```

**Concepts practised:** chaining prompts, LCEL.

**Note:** three model steps, so three API calls per run. Budget accordingly.

## Module 05 - Document Processing

**Topics:** PDF loader, DOCX loader, TXT loader, RecursiveCharacterTextSplitter,
token splitter.

**Mini project: PDF Chunk Viewer.** Load a document and visualise how LangChain
splits it into chunks.

**Concepts practised:** document loading, chunking, metadata.

**Extra dependencies:** `langchain-community`, `langchain-text-splitters`,
`pypdf`, `python-docx`, `tiktoken`. Fully offline, so it costs no quota at all.

**Note:** `langchain-community` now warns that it is being sunset. It still
holds the only PDF loader without a standalone replacement, so it is used with
the warning suppressed. The module also writes one loader by hand to show how
little a loader actually is.

## Module 06 - Embeddings

**Topics:** embeddings, cosine similarity, semantic search.

**Mini project: Sentence Similarity Checker.** Compare two sentences and
calculate semantic similarity.

**Concepts practised:** embeddings, similarity search.

**Note:** uses `GoogleGenerativeAIEmbeddings`, which has its own quota separate
from the chat models.

## Module 07 - Vector Databases

**Topics:** Chroma, FAISS, metadata, similarity search.

**Mini project: Personal Notes Search.** Store notes in a vector database and
retrieve them semantically.

**Concepts practised:** Chroma, embedding storage, retrieval.

**Extra dependencies:** `langchain-chroma`, `chromadb`, `faiss-cpu`.

**Note:** `similarity_search_with_score` returns a distance, not a similarity,
so lower is better. Sorting by it the obvious way gives the worst results
first. The module README documents the measured behaviour of both stores.

## Module 08 - Basic RAG

**Topics:** retriever, context, prompt plus retrieval.

**Mini project: Chat with One PDF.** Answer questions about a PDF using RAG.

**Concepts practised:** the full RAG pipeline.

**Note:** two API calls per question, one to embed it and one to answer. The
`show` command retrieves without calling the chat model, which is the cheap way
to check whether the right chunk was found.

**Finding:** removing the "answer only from the context" instruction did not
cause hallucination on the model tested. What it did change was citations and a
fixed refusal string. The module README records the measurements.

## Module 09 - Advanced RAG

**Topics:** MultiQueryRetriever, ParentDocumentRetriever, context compression,
SelfQueryRetriever.

**Mini project: Multi-PDF Research Assistant.** Answer questions across several
documents.

**Concepts practised:** advanced retrieval, multi-document search.

**Extra dependencies:** `lark`, for the SelfQueryRetriever query parser.
`langchain-classic` already ships with LangChain.

**Note:** MultiQueryRetriever makes one LLM call to rewrite the question and
then one search per rewrite, so a single question costs several requests. This
is the most quota-hungry module in the course. The `show` and `compare`
commands exercise retrievers without generating an answer.

**Version break:** `langchain.retrievers` does not exist in LangChain 1.x. All
of these retrievers moved to `langchain_classic`. Any tutorial importing from
`langchain.retrievers` fails on this version.

## Module 10 - Retrieval Optimization

**Topics:** BM25, hybrid search, cross encoder, reranking.

**Mini project: Search Comparison Demo.** Compare keyword, semantic, hybrid and
reranked results on the same query.

**Concepts practised:** search quality, retrieval optimisation.

**Extra dependencies:** `rank_bm25` and `FlashRank`.

**Change made:** the original outline listed Cohere Rerank, which needs a
separate account and API key. A local cross encoder does the same job offline.
`sentence-transformers` was the obvious choice but pulls in PyTorch, about 2 GB.
`flashrank` runs the same class of model on `onnxruntime`, which `chromadb`
already installs, so it added 0.1 MB instead.

**Finding:** reranking made results worse on this corpus. Across three test
queries it improved the top result in zero cases and worsened it in one, with
both a small and a large cross encoder. The module README explains why, and the
point is that this is an empirical question about your own data rather than a
rule to follow.

## Module 11 - Agents

**Topics:** tool calling, ReAct, StructuredTool, agent executors.

**Mini project: AI Utility Agent.** The agent chooses between a calculator, a
Wikipedia lookup and a weather lookup.

**Concepts practised:** tool calling, agent reasoning.

**Extra dependencies:** none beyond `requests`. Agents loop, so one question
costs one chat call per turn of the loop.

**Change made:** the outline assumed a weather API key and the `wikipedia`
package. Neither is needed. Open-Meteo provides weather and geocoding with no
key or account. The `wikipedia` package is unusable anyway, since Wikipedia now
returns 403 without a User-Agent header and that package sends none, so the tool
calls the API directly.

**Version break:** `AgentExecutor`, `initialize_agent` and `create_react_agent`
are gone from `langchain.agents`. The current API is `create_agent`, built on
LangGraph. The old names remain in `langchain_classic.agents`.

## Module 12 - Memory

**Topics:** buffer memory, summary memory, chat history.

**Mini project: Personal AI Assistant.** A chatbot that remembers earlier turns
in a session.

**Concepts practised:** memory, conversation history.

**Extra dependencies:** none.

**Version break:** `ConversationBufferMemory` and `ConversationChain` are gone
from `langchain` 1.x. They survive deprecated in `langchain_classic`. The
current options are `trim_messages`, `SummarizationMiddleware` and LangGraph
checkpointers. Anything teaching `ConversationChain` predates this version.

**Finding:** summary memory was a net loss on a short conversation. It saved
about 6 percent of tokens against plain buffer memory and cost an extra API call
to produce the summary. It only pays off over dozens of turns. The module README
has the measurements.

## Module 13 - LangGraph

**Topics:** nodes, edges, state, conditional routing.

**Mini project: Research Workflow.**

```
Question -> Research -> Summarize -> Review -> Final Answer
```

**Concepts practised:** LangGraph, stateful workflows.

**Extra dependencies:** none. `langgraph` already ships with LangChain, and
`grandalf` from Module 04 draws the graph.

**Note:** two API calls per run, plus two per revision. The `show` command
prints the graph structure for free.

**Worth knowing:** `create_agent` in Module 11 is itself a LangGraph graph, so
this module reveals what was already running underneath. The reviewer approves a
good summary first time, so `--force-revisions` exists to exercise the loop
deliberately rather than waiting for a natural failure.

## Module 14 - MCP

**Topics:** MCP servers, MCP clients, resources, tools.

**Mini project: Local File Assistant.** Read local files through an MCP server
and answer questions about them.

**Concepts practised:** MCP integration, external resources.

**Extra dependencies:** `langchain-mcp-adapters`, `mcp`.

**Version pin:** `mcp` must stay below 2.0. `langchain-mcp-adapters` 0.3.1
imports `mcp.shared.context.RequestContext`, which mcp 2.0 removed, so the
adapter fails at import. mcp 2.0 also replaced `FastMCP` with `MCPServer`.

**Note:** three of the four client commands make no model call, so the server
can be built and tested without spending quota. Module 14 also added
`arun_with_fallback` to `common`, because MCP is async and the sync helper
cannot be called from inside a running event loop.

## Module 15 - Production AI

**Topics:** FastAPI, Docker, streaming, logging, authentication, LangSmith.

**Mini project: AI Chat API.** Expose a LangChain chatbot through a FastAPI REST
API.

**Concepts practised:** production deployment, API development.

**Extra dependencies:** `fastapi`, `uvicorn`. Docker must be installed
separately. LangSmith needs a free account.

**Note:** the image installs `15-Production-AI/requirements-api.txt`, five
packages, rather than the repository's full list. The API imports none of the
retrieval or MCP stack, and shipping it would add hundreds of megabytes.

**Not verified:** the Dockerfile has not been built, because the Docker daemon
was not running on this machine. Everything else in the module is tested, with
17 automated checks, 14 of which cost no quota.

---

## Progress

| Module | Status |
|--------|--------|
| 01 Models | complete |
| 02 Prompt Templates | complete |
| 03 Output Parsers | complete |
| 04 Chains | complete |
| 05 Document Processing | complete |
| 06 Embeddings | complete |
| 07 Vector Databases | complete |
| 08 Basic RAG | complete |
| 09 Advanced RAG | complete |
| 10 Retrieval Optimization | complete |
| 11 Agents | complete |
| 12 Memory | complete |
| 13 LangGraph | complete |
| 14 MCP | complete |
| 15 Production AI | complete |

## Final goal

After completing this guide I should be able to:

- Build AI applications using LangChain
- Process and retrieve information from documents
- Create Retrieval-Augmented Generation systems
- Develop AI agents with tool-calling capabilities
- Build stateful workflows using LangGraph
- Integrate external resources using MCP
- Deploy production-ready AI APIs with FastAPI
- Apply best practices for modern AI engineering

## Notes

- Every module has its own `README.md` with commands and expected output.
- Every project is small and focused on one concept.
- Each project should be completed before moving to the next module.
- Each module README records what actually went wrong while building it, not
  just the happy path. That section is usually the most useful part.
- Dependencies are added when the module that needs them is reached, rather than
  installing everything up front.
