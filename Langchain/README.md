# LangChain Learning Journey

Hands-on LangChain practice, built as 15 small projects. Each module covers one
concept and is meant to be completed before moving to the next.

See [guide.md](guide.md) for the roadmap and the goal of each module.

## Contents

- [The modules](#the-modules) - the index, with a link to every module README
- [Provider](#provider)
- [Setup](#setup)
- [Choosing a model](#choosing-a-model)
- [The daily quota and automatic fallback](#the-daily-quota-and-automatic-fallback)
- [Project layout](#project-layout)
- [Thinking budget](#thinking-budget)
- [Running a module](#running-a-module)
- [Troubleshooting](#troubleshooting)
- [Version notes](#version-notes)

Two other documents sit alongside this one:

| Document | What it is for |
|----------|----------------|
| [MODULES.md](MODULES.md) | Folder by folder detail: contents, how each works, why, and what came out of it |
| [guide.md](guide.md) | The original roadmap and per-module plan, updated as things were built |

## Provider

All modules use Google Gemini through `langchain-google-genai`. Gemini covers
both chat and embeddings with a single API key, which keeps the later retrieval
modules (06 to 10) working without extra setup.

## Setup

Run these once from the repository root. One virtual environment is shared by
all fifteen modules, so do not create a separate one per module folder.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then open `.env` and set `GOOGLE_API_KEY`. Get a key from
https://aistudio.google.com/apikey - the free tier is enough for these projects.

`.env` lives at the repository root and is read by every module. Scripts find it
by searching upward from the folder they run in, so there is no need to copy it
into each module.

## Choosing a model

`.env` sets `GEMINI_MODEL`, which every module reads. The default is
`gemini-3.5-flash`.

Model availability changes, and two things make this less obvious than it looks:

- **Being listed does not mean being usable.** The API advertises models that
  are already retired for new requests. `gemini-2.5-flash` is one of them: it
  appears in the model list and returns 404 when called.
- **Older models get dropped from the free tier.** They then fail with a 429
  whose quota limit is literally `0`. That reads like "you used up your quota"
  but actually means "you never had any". `gemini-2.0-flash` behaves this way.

To find a model that genuinely works with your key:

```powershell
cd 01-Models
python list_models.py --probe
```

That sends one tiny request per candidate model and reports which are usable,
retired, or out of quota. Put a working name into `GEMINI_MODEL` in `.env`.

Things worth knowing when picking:

- **Pro models have no free tier.** `gemini-pro-latest` and the `3.x-pro`
  variants all report zero quota on a free key. Stick to `flash`.
- **Prefer a concrete name over an alias.** `gemini-flash-latest` works, but it
  points at a different model over time, so results can change under you
  partway through the course. A pinned name like `gemini-3.5-flash` keeps the
  modules reproducible.
- **Some models ignore `temperature`.** `gemini-3.6-flash` warns that it uses
  fixed sampling defaults, which makes Module 01's temperature comparison
  meaningless on it.
- **Not every model accepts `thinking_budget`.** See below.

## The daily quota and automatic fallback

The free tier allows **20 requests per day, per model, per project**. Not per
minute. The quota is `GenerateRequestsPerDayPerProjectPerModel-FreeTier`.

Twenty calls goes quickly, so the modules fall back automatically. When a model
runs out, the next one in the list is tried without you doing anything:

```
[gemini-3.5-flash is out of quota, trying the next model]
Why did the traffic light turn red?
```

Configure the chain in `.env`:

```
GEMINI_MODEL=gemini-3.5-flash
GEMINI_FALLBACK_MODELS=gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-3.5-flash-lite
GOOGLE_API_KEYS=
```

With four models that is 80 requests a day on one key.

### Adding more keys

The quota is counted **per project**, not per account. So the supported way to
get more is to create additional Google Cloud projects and generate a key in
each:

1. Create a project at https://console.cloud.google.com/projectcreate
2. Generate a key for it at https://aistudio.google.com/apikey
3. Add it to `GOOGLE_API_KEYS` in `.env`, comma separated

Models rotate within a key first, then it moves to the next key. Two projects
with four models gives 160 requests a day.

Note that this is different from creating extra Google **accounts** to dodge the
limit. That is against Google's terms of service and risks all of the accounts
involved. Extra projects under your own account are a normal, supported thing to
do; extra accounts are not.

### Spending less

- Iterate offline. `--show-prompt` in Modules 02 and 03 renders a prompt without
  calling the API.
- Reserve live calls for when the prompt already looks right.
- Quotas reset at midnight Pacific time.

## Project layout

```
common/          shared boilerplate only
  errors.py      classifies provider errors into readable messages
  models.py      model construction and the quota fallback chain
01-Models/ ...   one folder per module, each self contained
```

`common/` deliberately holds only boilerplate. Model construction arguments,
prompts and parsers stay in each module's own file, because those are the
lesson. Module scripts add the repository root to `sys.path` so `common` imports
regardless of which folder you run from:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import run_with_fallback
```

## Thinking budget

Current Gemini models run an internal reasoning step before answering, and those
reasoning tokens count against `max_output_tokens`. For short answers this can
consume the entire budget and truncate the reply. `GEMINI_THINKING_BUDGET=0` in
`.env` switches reasoning off.

Not every model accepts the parameter, but this is handled automatically: a
model that rejects it is retried once without it. These reject it with a 400:

| Model | `thinking_budget=0` |
|-------|---------------------|
| `gemini-3.5-flash` | accepted |
| `gemini-3.1-flash-lite` | accepted |
| `gemini-3-flash-preview` | accepted |
| `gemini-3.5-flash-lite` | 400 error |
| `gemini-3.6-flash` | 400 error |
| `gemma-4-31b-it` | 400 error |

If you hit a 400, set `GEMINI_THINKING_BUDGET=` (empty) to stop sending it. The
models that reject it mostly do not reason by default anyway, so little is lost.

## Running a module

Each module folder is self contained and has its own README with commands.
Activate the shared environment first.

```powershell## What to try next

- Run `compare` on five questions where you know the right article, and count
  how often each method puts it first. That is a tiny evaluation set, and it is
  how the reranking finding above was reached.
- Change `weights` to `[0.8, 0.2]` in `make_retriever` to favour BM25, and rerun
  the RAM query.
- Search for `ERR_5150` and check whether semantic search confuses it with
  `ERR_4021`.
- Add an article of your own with a rare product name, then query that name.
  Watch BM25 nail it and semantic search struggle.
.\venv\Scripts\Activate.ps1
cd 01-Models
python joke_generator.py "space travel"
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `GOOGLE_API_KEY is not set` | No `.env`, or the key line is empty | Copy `.env.example` to `.env` at the repository root and fill in the key |
| 429, quota `limit: 0` | The model has no free tier allocation | Run `list_models.py --probe`, set a usable `GEMINI_MODEL` |
| 429, quota `limit: 20`, `PerDay` | Daily cap used up for that model | Switch `GEMINI_MODEL` to another usable model for a fresh 20, or wait until midnight Pacific |
| 429, "rate limit reached" | Too many requests per minute | Wait a minute. Modes that make several calls hit it first |
| 400 `INVALID_ARGUMENT` | The model rejects `thinking_budget` | Set `GEMINI_THINKING_BUDGET=` (empty) in `.env` |
| `temperature will be ignored` warning | The model uses fixed sampling defaults | Use a model that honours `temperature`, such as `gemini-3.5-flash` |
| 404 / "no longer available" | The model is retired | Run `list_models.py --probe`, set a usable `GEMINI_MODEL` |
| "The API key was rejected" | Wrong or revoked key | Create a new key at https://aistudio.google.com/apikey |
| Answer is cut off mid sentence | Reasoning tokens ate the output budget | Pass `thinking_budget=0`, or raise `max_output_tokens`. See [Module 01](01-Models/README.md#thinking-models) |
| Output prints as `[{'type': 'text', ...}]` | `.content` is a list of content blocks | Use `response.text`, not `response.content` |

Scripts print a short explanation rather than a traceback. Add `--debug` to any
module script to see the full traceback instead.

## The modules

All fifteen are complete. Every folder has its own README with commands,
expected output, and a record of what went wrong while building it.

For a longer account of what each folder contains, how it works, why it is built
that way and what came out of it, see **[MODULES.md](MODULES.md)**.

| Module | Topics | Cost per run | Notes |
|--------|--------|--------------|-------|
| [01 Models](01-Models/README.md) | chat models, temperature, max tokens, streaming, structured output | 1 call, 3 for `--mode temperature` | `list_models.py --probe` finds a model that actually works |
| [02 Prompt Templates](02-Prompt-Templates/README.md) | PromptTemplate, ChatPromptTemplate, variables, few-shot | 1 call, `--show-prompt` is free | few-shot beat writing more rules |
| [03 Output Parsers](03-Output-Parsers/README.md) | Str, Json and Pydantic parsers, generated format instructions | 1 call | the schema writes part of the prompt |
| [04 Chains](04-Chains/README.md) | LCEL, RunnableSequence, RunnableLambda, `.assign` | 3 calls, `--show-graph --dry-run` is free | includes a hand written equivalent to compare |
| [05 Document Processing](05-Document-Processing/README.md) | PDF, DOCX and TXT loaders, three splitters, metadata | **free, fully offline** | `chunk_size` is a target, not a guarantee |
| [06 Embeddings](06-Embeddings/README.md) | embeddings, cosine similarity, semantic search, `task_type` | 1 call, batched | absolute similarity scores are nearly meaningless |
| [07 Vector Databases](07-Vector-Databases/README.md) | Chroma, FAISS, metadata filtering, persistence | 1 call, `stats` is free | `similarity_search_with_score` returns a distance |
| [08 Basic RAG](08-Basic-RAG/README.md) | retrievers, context assembly, grounding, citations | 2 calls, `show` costs 1 | grounding did not prevent hallucination |
| [09 Advanced RAG](09-Advanced-RAG/README.md) | MultiQuery, ParentDocument, compression, SelfQuery | 1 to 4 calls, `compare` skips answering | the most expensive module |
| [10 Retrieval Optimization](10-Retrieval-Optimization/README.md) | BM25, hybrid search, cross encoder reranking | 3 embed calls, keyword is free | reranking made results worse |
| [11 Agents](11-Agents/README.md) | tool calling, StructuredTool, agent loops, ReAct | 1 call per loop turn, `tools` is free | no API keys beyond Gemini |
| [12 Memory](12-Memory/README.md) | buffer, window and summary memory, chat history | 4 calls per demo, `threads` is free | summary memory was a net loss |
| [13 LangGraph](13-LangGraph/README.md) | nodes, edges, state, conditional routing | 2 calls plus 2 per revision, `show` is free | one backwards edge is the whole point |
| [14 MCP](14-MCP/README.md) | MCP servers and clients, tools, resources | 3 of 4 commands are free | `mcp` must stay below 2.0 |
| [15 Production AI](15-Production-AI/README.md) | FastAPI, streaming, logging, auth, Docker | 14 tests are free, 3 are live | Dockerfile written but not built |

Shared code lives in [`common/`](common/), which holds only boilerplate: error
classification and the quota fallback chain. See
[MODULES.md](MODULES.md#shared-code) for why the boundary is drawn there.

## Version notes

This repository uses **LangChain 1.x**. Most tutorials, courses and blog posts
still target 0.x, where import paths and several APIs differ. When following
outside material, check which version it was written for.

The differences that have actually come up so far:

| Topic | 0.x | 1.x |
|-------|-----|-----|
| Reading a reply | `response.content` was a string | `response.content` is a list of content blocks; use `response.text` |
| `.text` | did not exist | a property, not a method - calling `.text()` is deprecated |
| Retrievers | `langchain.retrievers` | `langchain_classic.retrievers` |
| `AttributeInfo` | `langchain.chains.query_constructor.schema` | `langchain_classic.chains.query_constructor.schema` |
| Document loaders | `langchain.document_loaders` | `langchain_community.document_loaders`, now being sunset |

The `langchain` package itself is now small. It contains only `agents`,
`chat_models`, `embeddings`, `messages`, `rate_limiters` and `tools`. Almost
everything a 0.x tutorial imports from `langchain.something` has moved to
`langchain_classic` or a dedicated integration package.

Exact pinned versions are in [requirements.txt](requirements.txt).
