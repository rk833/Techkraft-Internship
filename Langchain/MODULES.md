# Module Walkthrough

A folder by folder account of this repository: what is in each one, what it
teaches, how it works, why it was built that way, and what I took away from it.

Each module also has its own README with commands and expected output. This file
is the map; those are the detail.

- [How to read this](#how-to-read-this)
- [Shared code](#shared-code)
- [Module 01 - Models](#module-01---models)
- [Module 02 - Prompt Templates](#module-02---prompt-templates)
- [Module 03 - Output Parsers](#module-03---output-parsers)
- [Module 04 - Chains](#module-04---chains)
- [Module 05 - Document Processing](#module-05---document-processing)
- [Module 06 - Embeddings](#module-06---embeddings)
- [Module 07 - Vector Databases](#module-07---vector-databases)
- [Module 08 - Basic RAG](#module-08---basic-rag)
- [Module 09 - Advanced RAG](#module-09---advanced-rag)
- [Module 10 - Retrieval Optimization](#module-10---retrieval-optimization)
- [Module 11 - Agents](#module-11---agents)
- [Module 12 - Memory](#module-12---memory)
- [Module 13 - LangGraph](#module-13---langgraph)
- [Module 14 - MCP](#module-14---mcp)
- [Module 15 - Production AI](#module-15---production-ai)
- [Lessons that run through the whole course](#lessons-that-run-through-the-whole-course)
- [Where the original plan was wrong](#where-the-original-plan-was-wrong)

## How to read this

The modules build on each other. Roughly:

```
01-04   the four primitives: model, prompt, parser, chain
05-07   getting your own data into a form a model can search
08-10   retrieval augmented generation, then making retrieval good
11      letting the model act instead of only answering
12-13   state: remembering a conversation, and controlling a workflow
14-15   taking it outside the process: a protocol, then a service
```

Almost every module reuses something from an earlier one. Where that happens it
is called out, because those links are the point of doing them in order.

---

## Shared code

**Folder:** `common/`

Boilerplate only. Anything that is part of a module's lesson stays in that
module's own file, so each project can still be read end to end without jumping
between folders.

| File | Purpose |
|------|---------|
| `errors.py` | Classifies provider errors and turns them into short, actionable messages |
| `models.py` | Chat model construction, and the quota fallback chain |
| `embeddings.py` | Embedding model construction, same fallback approach |
| `sample_pdf.py` | Writes a small PDF by hand, used to generate fixtures in Modules 05 and 08 |

### Why it exists

It did not, at first. Modules 01 and 02 each had their own copy of model
construction and error handling, and by the time the same block had been edited
in two places three times it was clearly going to drift.

The rule settled on: **`common/` holds things that are not the lesson.** Error
message wording is not a LangChain concept. Constructor arguments are, so those
stayed in each module.

### The quota fallback

The Gemini free tier allows 20 requests per day, per model, per project. That is
easy to exhaust halfway through building something, so `run_with_fallback`
rotates automatically:

```
[gemini-3.5-flash is out of quota, trying the next model]
```

Only quota exhaustion moves to the next candidate. Every other error is raised
immediately, because a fallback that swallows real bugs is worse than no
fallback. A model that rejects `thinking_budget` is retried once without it.

`arun_with_fallback` is the async twin, added in Module 14 when MCP forced the
whole call path to be async.

### What I learned

Shared code earns its place by being edited, not by being predicted. Waiting
until the third duplicate made the boundary obvious in a way that designing it
up front would not have.

---

## Module 01 - Models

**Folder:** [`01-Models/`](01-Models/) - [README](01-Models/README.md)

| File | Purpose |
|------|---------|
| `joke_generator.py` | The mini project. Four modes, one per topic. |
| `list_models.py` | Finds a model name that actually works with your key |

**Topics:** chat models, temperature, max output tokens, streaming, structured
output.

### How it works

`python joke_generator.py "space travel"` sends one prompt and prints the reply
plus its token usage. Three other modes isolate one behaviour each:

- `--mode temperature` runs the same prompt at 0.0, 0.7 and 1.5
- `--mode stream` prints chunks as they arrive rather than waiting
- `--mode structured` returns a typed `Joke` object via
  `with_structured_output`

### Why it is built this way

One script with modes rather than four scripts, so the only difference between
them is the behaviour being demonstrated.

`list_models.py` exists because of a mistake. The first version of this module
defaulted to `gemini-2.0-flash` and told the reader to verify it with a model
listing. Both were wrong.

### What I learned

**The model list lies.** `gemini-2.5-flash` is advertised by the API and returns
404 when called. `gemini-2.0-flash` returns a 429 whose quota limit is literally
`0`, which reads like "you used it up" but means "you never had any". Hence
`list_models.py --probe`, which sends a tiny real request to each candidate.

**Reasoning tokens count against your output budget.** The first working call
spent 243 of 252 output tokens thinking, so the joke was cut off before the
punchline and structured output failed entirely. `thinking_budget=0` fixed it.
Then it turned out several models reject that parameter outright, so it had to
become configurable rather than hardcoded.

**`response.content` is not a string in LangChain 1.x.** It is a list of content
blocks. Printing it dumps internal structure including a base64 signature. Use
`.text`.

**Temperature is less dramatic than expected.** In one run, 0.7 and 1.5 produced
the same joke. There are only so many jokes about a topic, so a few completions
dominate the probability mass even after temperature flattens it. The README
says so rather than pretending otherwise.

---

## Module 02 - Prompt Templates

**Folder:** [`02-Prompt-Templates/`](02-Prompt-Templates/) - [README](02-Prompt-Templates/README.md)

| File | Purpose |
|------|---------|
| `headline_generator.py` | Three prompt styles, same task |

**Topics:** `PromptTemplate`, `ChatPromptTemplate`, variables, few-shot
prompting.

### How it works

Generates LinkedIn headlines from skills and a career goal, three ways:

| Mode | Builds |
|------|--------|
| `simple` | one string with placeholders |
| `chat` | role tagged system and human messages |
| `fewshot` | worked examples inserted as fake prior turns |

`--show-prompt` renders the filled prompt without calling the API.

### Why it is built this way

Same input through all three, so the differences are attributable to prompt
structure and nothing else. `--show-prompt` exists because prompt work is
iterative and the free tier is 20 calls a day; rendering is free.

### What I learned

The three modes produce visibly different output from identical input:

```
simple   Aspiring Data Engineer | Python, SQL & Airflow Enthusiast | Building Scalable...
chat     Data Engineer | Python | SQL | Airflow
fewshot  Data Engineer | Python, SQL, Airflow | Building scalable data pipelines
```

**`simple` reaches for filler.** "Enthusiast", "Passionate about". Nothing told
it not to.

**`chat` obeys rules better**, because a no-buzzwords instruction in a system
message carries more weight than the same words in a paragraph.

**`fewshot` matched a format no rule described.** Two examples fixed the house
style exactly. When a prompt keeps producing almost-right formatting, adding
examples beats adding more rules.

Also learned here: the free tier limit is **per day, per model**, not per
minute, so switching models buys a fresh allowance immediately. That discovery
is what led to the fallback chain in `common/`.

---

## Module 03 - Output Parsers

**Folder:** [`03-Output-Parsers/`](03-Output-Parsers/) - [README](03-Output-Parsers/README.md)

| File | Purpose |
|------|---------|
| `review_analyzer.py` | Three parsers, same task |
| `sample_review.txt` | A deliberately mixed film review |

**Topics:** `StrOutputParser`, `JsonOutputParser`, `PydanticOutputParser`.

### How it works

Turns a free text review into structured data. `--mode str` returns prose,
`--mode json` a `dict`, `--mode pydantic` a validated `ReviewAnalysis` object.
`--show-prompt` reveals the format instructions the parser generated.

The sample review is mixed on purpose: praise and complaints in one text, so a
lazy "everything is positive" answer is visibly wrong.

### Why it is built this way

The interesting part is not parsing, it is that the parser writes part of the
prompt. Both JSON and Pydantic parsers generate format instructions from the
schema and inject them, so the schema is prompt engineering.

### What I learned

**Everything in the Pydantic class is sent to the model.** My first version had
a long docstring explaining the teaching point of the class, and all of it went
into the prompt as instructions. Field descriptions are instructions too, not
comments, and they cost input tokens on every call.

**`JsonOutputParser` does not validate.** Given a schema it generates
instructions from it, then returns whatever dict came back. A rating of
`"seven"` passes straight through and fails somewhere else later.
`PydanticOutputParser` fails at the boundary, which is where you want it.

**Parsers and `with_structured_output` are different mechanisms.** The former
puts instructions in the prompt and parses text; the latter uses the provider's
native structured output. Native is more reliable and cheaper; parsers work with
any model that emits text.

**`StrOutputParser` returns a `TextAccessor`, not a `str`,** in LangChain 1.x. It
behaves like a string but `isinstance(x, str)` is `False`.

---

## Module 04 - Chains

**Folder:** [`04-Chains/`](04-Chains/) - [README](04-Chains/README.md)

| File | Purpose |
|------|---------|
| `story_generator.py` | Topic to title to story to summary, in LCEL and by hand |

**Topics:** LCEL, `RunnableSequence`, `RunnableLambda`,
`RunnablePassthrough.assign`.

### How it works

Three chained model steps. `--show-graph --dry-run` prints the pipeline
structure without calling anything. `--mode manual` performs the identical work
written out imperatively, for comparison.

### Why it is built this way

The manual mode is the point. LCEL is easy to accept uncritically; putting the
two side by side makes the trade explicit.

### What I learned

**`RunnablePassthrough.assign` is what makes multi-step chains work.** A chain
passes one value along, but the story step needs both the topic and the title.
`.assign` adds a key while keeping everything already there, so the dictionary
grows as it flows.

**Not every chain step calls a model.** `count_words` is a `RunnableLambda` that
costs nothing, and `clean_title` repairs model output before a later step
depends on it. Fixing a value once, where it is produced, beats defending
against it everywhere downstream.

**LCEL is close to a tie at three steps.** It removes plumbing and makes the
structure inspectable, which is what gives you streaming and graph drawing for
free. It also debugs worse. It wins as chains grow, not automatically.

**Two bugs I would not have found without running it.** Windows console encoding
mangled a curly apostrophe into `The Keeper?s Vigil`, fixed centrally by
switching stdout to UTF-8. And `clean_title` was a naive chain of `.strip()`
calls that turned `"Title".` into `Title"`, because the full stop outside the
quote protected it. The fix strips quotes only as a matched pair, in a loop.

---

## Module 05 - Document Processing

**Folder:** [`05-Document-Processing/`](05-Document-Processing/) - [README](05-Document-Processing/README.md)

| File | Purpose |
|------|---------|
| `chunk_viewer.py` | Loads a document and shows exactly how it splits |
| `make_samples.py` | Writes the same text as `.txt`, `.docx` and `.pdf` |
| `sample.*` | Generated fixtures, gitignored |

**Topics:** PDF, DOCX and TXT loaders, `RecursiveCharacterTextSplitter`,
`CharacterTextSplitter`, `TokenTextSplitter`, metadata.

### How it works

Entirely offline, no API calls. `--show-overlap` recovers the text actually
shared between neighbouring chunks by comparison, since splitters do not report
it. `--compare` runs all three splitters on the same document.

### Why it is built this way

The same content is written as three file types so loader differences are
visible rather than described. The PDF is generated by writing PDF syntax
directly rather than adding a PDF library just to make a fixture.

### What I learned

**`chunk_size` is a target, not a guarantee.** `CharacterTextSplitter` returned
642 and 650 character chunks against a limit of 400, because PDF-extracted text
has no blank lines to split on. Recursive handled the same document correctly.
Run the comparison on the `.txt` version and they agree exactly, so the splitter
is not bad, it is sensitive to the document.

**Overlap never crosses a page boundary.** `PyPDFLoader` returns one Document
per page, splitting happens per document, so anything spanning a page break
loses its context.

**Overlap costs storage.** 10.8 percent more text than the original in the
default run, and every repeated character gets embedded and stored again later.

**A loader is not magic.** `Docx2txtLoader` needs a package `python-docx` is
not, so I wrote the DOCX loader by hand in three lines. A loader is anything
returning `Document(page_content, metadata)`. That made `langchain-community`
being sunset much less frightening.

---

## Module 06 - Embeddings

**Folder:** [`06-Embeddings/`](06-Embeddings/) - [README](06-Embeddings/README.md)

| File | Purpose |
|------|---------|
| `similarity_checker.py` | Four modes: demo, pair, search, matrix |
| `sample_sentences.txt` | Ten sentences including deliberate homonyms |

**Topics:** embeddings, cosine similarity, semantic search, `task_type`,
normalisation.

### How it works

One batched request per run, regardless of how many sentences. Cosine similarity
is written out rather than imported. `--mode matrix` compares every sentence with
every other.

### Why it is built this way

The corpus contains planted homonyms - "bank" as finance and as riverside,
"python" as language and as snake - so the matrix shows disambiguation rather
than asserting it.

### What I learned

**This module changed how I read every number afterwards.** Textbooks say cosine
similarity runs -1 to 1 with 0 meaning unrelated. Measured on
`gemini-embedding-001`:

| Comparison | Score |
|------------|-------|
| identical text | 1.000 |
| completely unrelated sentences | **0.749** |

Nothing fell below 0.7. A tutorial rule like "similar means above 0.5" would
call everything a strong match. Worse, the range moves with `task_type`: the same
model gave 0.75 to 1.00 in one mode and 0.57 to 0.67 in another.

**Rank, do not threshold.** My own first thresholds were invented and labelled
the deliberately unrelated pair "loosely related". They are now calibrated from
measurements and documented as model specific.

**Truncated vectors are not unit length.** Full size 3072 dimensions have an L2
norm of exactly 1.000; truncate to 768 and it is 0.578. Cosine survives because
it divides by both norms, but a plain dot product does not, and vector databases
use dot product. That would have silently degraded results in Module 07.

**Batching is what keeps embeddings cheap.** Cost scales with requests, not text.

---

## Module 07 - Vector Databases

**Folder:** [`07-Vector-Databases/`](07-Vector-Databases/) - [README](07-Vector-Databases/README.md)

| File | Purpose |
|------|---------|
| `notes_search.py` | build, search, compare, stats |
| `sample_notes.txt` | Ten notes across three categories |
| `chroma_db/`, `faiss_index/` | Generated stores, gitignored |

**Topics:** Chroma, FAISS, metadata filtering, similarity search, persistence.

### How it works

`build` embeds every note in one batch and writes to disk. `search` then only
has to embed the query. `stats` costs nothing at all.

### Why it is built this way

That split is the entire argument for a vector database, so the cost of each
command is printed. Chroma is the default because it is in a maintained package
and filters on metadata properly; FAISS is included for comparison.

### What I learned

**`similarity_search_with_score` returns a distance, not a similarity.** Verified
with a controlled fake embedder where I knew the true answers:

| True cosine similarity | Chroma "score" |
|------------------------|----------------|
| 1.00 identical | **0.00** |
| 0.00 orthogonal | **2.00** |

Sorting by that descending gives the worst matches first, and the code looks
perfectly reasonable while doing it.

**The provided helper is not a fix.** `similarity_search_with_relevance_scores`
claims to normalise to 0-1 and returned **-0.4142** on the same test.

**A vector store always returns k results.** Asked "booking a flight to Tokyo"
against notes containing nothing about flights, it confidently returned three,
and the top hit was **"Token limits"** matching "Tokyo" on surface form. The
tells are a flat score spread and scores worse than a real query's top hit, not
the absolute number.

**Metadata must exist before you store.** Filtering happens inside the database,
so adding a field later means rebuilding.

---

## Module 08 - Basic RAG

**Folder:** [`08-Basic-RAG/`](08-Basic-RAG/) - [README](08-Basic-RAG/README.md)

| File | Purpose |
|------|---------|
| `rag_chat.py` | build, show, ask |
| `make_sample.py` | Writes `handbook.pdf` |

**Topics:** retrievers, context assembly, grounding prompts, citations.

### How it works

Assembles Modules 05 to 07 into a pipeline: load, chunk, embed, store, retrieve,
answer. `show` retrieves and prints without calling the chat model, which is the
cheap way to check whether the right chunk was found.

The handbook deliberately omits several obvious topics, so refusal behaviour is
testable.

### Why it is built this way

`--no-grounding` removes the "answer only from the context" instructions, so
their effect can be measured instead of assumed.

### What I learned

**The tutorial claim did not reproduce.** Standard RAG material says that without
grounding instructions the model hallucinates. I tested four times with
`--no-grounding` and **it never happened** - the model refused honestly every
time, unprompted.

What grounding did buy, consistently:

- **Citations.** Grounded answers cite `(page 1)`; ungrounded ones never cite.
- **A fixed refusal string.** Grounded refusals are always exactly
  `I don't know based on the handbook.`, which can be detected in code.
  Ungrounded refusals are prose that varies every run.

So grounding is cheap insurance and a formatting contract, not a magic
hallucination switch. Keeping it is still right, because it converts luck into a
contract and smaller models behave worse.

**The model cannot see metadata.** Only `page_content` is sent, so page numbers
have to be written into the context text. Asking for citations without doing
that invites invented page numbers.

**Retrieval quality caps everything.** No prompt recovers from a bad retrieve.
When a RAG answer is wrong, check what was retrieved before touching the prompt.

---

## Module 09 - Advanced RAG

**Folder:** [`09-Advanced-RAG/`](09-Advanced-RAG/) - [README](09-Advanced-RAG/README.md)

| File | Purpose |
|------|---------|
| `research_assistant.py` | Five retrievers, four commands |
| `make_samples.py` | Writes three department PDFs |

**Topics:** `MultiQueryRetriever`, `ParentDocumentRetriever`, contextual
compression, `SelfQueryRetriever`, multi-document search.

### How it works

Three documents owned by different departments, written to overlap and partly
disagree. `compare` runs several retrievers on one question with no answer
generation, which is where the differences actually are.

### Why it is built this way

This is the most expensive module, so every retriever can be exercised in
retrieval-only mode. Costs are tabulated per retriever in the README.

### What I learned

**Retrievers move in opposite directions**, and neither is simply better:

```
basic         4 chunks, 2 documents
multiquery    5 chunks, 3 documents    higher recall, lower precision
compression   2 chunks, 2 documents    higher precision, risk of dropping
```

**SelfQuery turns language into a filter.** "What do the engineering docs say"
became `department = engineering`, and it returned 2 chunks for `--top 3`
because filtering left only two candidates. Unlike plain similarity search, a
filtered search can return fewer than k.

**One prompt line earned its place:** "When two documents disagree or overlap,
say so explicitly." The answer then flagged that one document required a police
reference number the other omitted.

**The biggest version break in the course.** `langchain.retrievers` does not
exist in 1.x. The `langchain` package now holds only `agents`, `chat_models`,
`embeddings`, `messages`, `rate_limiters`, `tools`. Everything moved to
`langchain_classic`.

**An import error naming an unrelated product usually means auto-detection.**
`SelfQueryRetriever.from_llm` failed with `cannot import name
'DatabricksVectorSearch'` because it inspects the store by importing every
supported vector store. Passing the translator explicitly skips it.

---

## Module 10 - Retrieval Optimization

**Folder:** [`10-Retrieval-Optimization/`](10-Retrieval-Optimization/) - [README](10-Retrieval-Optimization/README.md)

| File | Purpose |
|------|---------|
| `search_comparison.py` | keyword, semantic, hybrid, reranked |
| `support_articles.txt` | Ten articles written to make the methods disagree |

**Topics:** BM25, hybrid search with reciprocal rank fusion, cross encoder
reranking.

### How it works

`compare` runs one query through all four methods and prints the rankings side
by side. BM25 costs nothing and needs no index on disk; the cross encoder runs
locally.

### Why it is built this way

The corpus contains deliberate rare tokens (`ERR_4021`) that favour BM25, and
problems described in vocabulary users would not use, which favours embeddings.

### What I learned

**Keyword and semantic fail differently.** On "our service gradually eats more
RAM until we bounce it", BM25 put the **spam folder article** first, because the
query says RAM/bounce/eats and the article says memory/restarted/climbs.
Semantic got it right. On `ERR_4021`, semantic's second hit was `ERR_5150` - it
recognised the shape of an error code without distinguishing which.

**Reciprocal rank fusion combines ranks, not scores**, which is exactly right
given Modules 06 and 07: BM25 scores and cosine distances are on unrelated
scales.

**Reranking made results worse.** Across three queries it improved the top result
in **zero** cases and worsened it in one, pushing a correct answer from rank 1 to
rank 4. I checked whether it was model size by testing a 4 MB and a 99 MB cross
encoder; both failed the same way. Likely domain mismatch, since these models are
trained on web search passages, plus a corpus too small for reranking to earn
anything. The lesson is not "rerankers are bad", it is that this is an empirical
question about your data.

**Writing an evaluation set is harder than it looks.** My first corpus failed
because the article about slow cold starts literally contained "hanging" and
"taking ages", handing BM25 the win. A test set where every method agrees
teaches nothing.

**Dependency choice matters.** The plan named `sentence-transformers`, which
pulls in PyTorch at about 2 GB. `flashrank` runs the same class of model on
`onnxruntime`, which `chromadb` already installs, so it added 0.1 MB.

---

## Module 11 - Agents

**Folder:** [`11-Agents/`](11-Agents/) - [README](11-Agents/README.md)

| File | Purpose |
|------|---------|
| `utility_agent.py` | The agent. `ask` and `tools`. |
| `tools.py` | Calculator, Wikipedia, weather |

**Topics:** tool calling, `StructuredTool`, agent loops, ReAct.

### How it works

`create_agent` builds a loop: call the model, run any tools it asked for, feed
results back, repeat until it stops asking. `tools` prints exactly what the model
sees, with no API call.

### Why it is built this way

Tools live in their own file to make the point that they are ordinary Python.
Both external services were chosen to need no API key.

### What I learned

**The model decides, and it is genuinely surprising to watch.** Asked for the
temperature in Kathmandu in Fahrenheit, it called `weather`, **read `23.4 C` out
of a sentence of prose**, worked out the conversion formula, built
`23.4 * 9 / 5 + 32` and called the calculator. None of that is in the code.

It also issues independent calls in parallel, and sequential ones only when the
second depends on the first.

**The docstring is the prompt.** The model never sees the code. Name, description
and argument schema are its entire manual, and all three are sent with every
request. "Does not handle words, units, currency symbols" exists because without
it the model passes `"$18 * 4.5"`.

**Never use `eval` in a tool.** Tool arguments are written by a model, often
echoing user input. The calculator parses to a syntax tree and allows only
numbers and arithmetic operators, so `__import__('os').system(...)` is refused
structurally rather than by a blocklist there is no way to keep current.

**Agents over-call tools.** Asked for the capital of France it called Wikipedia,
obeying my own system prompt. Encourage tools and they get used unnecessarily;
discourage them and the model answers from memory when it should check.

**The `wikipedia` PyPI package does not work any more.** Wikipedia returns 403
without a User-Agent header and that package, last updated in 2014, sends none.
Calling the API directly removed a dependency.

---

## Module 12 - Memory

**Folder:** [`12-Memory/`](12-Memory/) - [README](12-Memory/README.md)

| File | Purpose |
|------|---------|
| `assistant.py` | Three strategies, three commands |

**Topics:** buffer memory, summary memory, chat history, trimming.

### How it works

`demo` replays a fixed four turn conversation so strategies are comparable. Turn
1 plants two facts, turn 4 asks for them back. `threads` shows conversation
isolation with no API call.

### Why it is built this way

The strategies are implemented by hand rather than with a framework. Using
`create_agent` with a checkpointer would have been six lines and taught nothing,
because the interesting part - deciding what to resend - would be hidden.

### What I learned

**The model is stateless.** Memory is your code keeping a list and resending it.
That one fact explains why memory costs tokens, why it needs strategies, and why
there is no server-side conversation to manage.

**The trade is visible in the token counts:**

| Strategy | Tokens at turn 4 | Remembered? | API calls |
|----------|-----------------|-------------|-----------|
| buffer | 208 | yes | 4 |
| window | 92 | **no** | 4 |
| summary | 195 | yes | **5** |

Buffer grows 45, 93, 149, 208 - quadratic across a conversation. Window is flat
and forgot the name entirely, answering "I don't have access to your personal
information" rather than "I have forgotten", because from its view the
conversation began two messages ago.

**Summary memory was a net loss here.** It saved 6 percent of tokens and cost an
extra API call. It only pays over dozens of turns. Do not reach for it because it
sounds sophisticated; count the tokens.

**The summary prompt decides what survives.** "Keep every concrete fact the user
stated about themselves, including names, numbers and preferences, even if they
seem trivial" is why it remembered. Without that, a summariser writes a
perfectly good summary that loses exactly what was needed.

---

## Module 13 - LangGraph

**Folder:** [`13-LangGraph/`](13-LangGraph/) - [README](13-LangGraph/README.md)

| File | Purpose |
|------|---------|
| `research_workflow.py` | Four nodes, one loop, one conditional edge |

**Topics:** nodes, edges, state, conditional routing.

### How it works

```
question -> research -> summarize -> review -> final answer
                             ^          |
                             +--revise--+
```

`show` prints the structure and the edge list for free. `run` streams each node
as it fires.

### Why it is built this way

`research` uses Wikipedia and `finalize` is pure Python, so two of the four nodes
cost nothing. That is deliberate: it shows the graph coordinates steps without
caring what they do.

### What I learned

**One edge is the whole module.** `review ..> summarize` points backwards, to a
node that has already run. A chain cannot express that.

**Routing needs structured output.** `review` returns a typed verdict, so the
router branches on a real boolean. A routing decision made by searching prose for
the word "approved" is one that eventually breaks.

**Looping only helps if something changes.** The reviewer's feedback is added to
the next prompt. Without it, pass two produces the same output as pass one and
the graph burns two calls per lap for nothing.

**Cycles need a cap, and the counter must sit on the cycle.** If it incremented
somewhere off the loop the cap would never trigger.

**An untested loop is an unverified loop.** The reviewer approved the summary
first time, even in strict mode, so the most interesting edge never fired. I
added `--force-revisions`, which rejects the first N attempts outright and costs
nothing. Waiting for a model to fail naturally is not a test, it is hoping.

**I had already been using LangGraph.** `create_agent` in Module 11 is a graph:
call model, asked for tools, run them, go back. Same conditional edge, same
cycle.

---

## Module 14 - MCP

**Folder:** [`14-MCP/`](14-MCP/) - [README](14-MCP/README.md)

| File | Purpose |
|------|---------|
| `file_server.py` | The MCP server. Standalone, knows nothing about LangChain. |
| `file_assistant.py` | The client. Discovers tools and gives them to an agent. |
| `notes/` | Four work notes, two of which deliberately disagree |

**Topics:** MCP servers, clients, tools, resources.

### How it works

The client launches the server as a subprocess and asks what it can do. Three of
the four client commands make no model call, so the server can be built and
debugged for free.

### Why it is built this way

Writing the server rather than consuming someone else's is what makes the
protocol concrete. The notes contain a deliberate conflict: on 14 July the answer
was "nobody knows", on 21 July it was resolved.

### What I learned

**The client never imports the server.** It learns the tool names, descriptions
and argument schemas at runtime, over a protocol. The entire integration is a
command and a transport:

```python
{"command": sys.executable, "args": [str(SERVER)], "transport": "stdio"}
```

Pointing at someone else's MCP server, written in TypeScript or Go, means editing
those lines and nothing else. Tools stop being library code and become a service.

**Tools and resources are different.** A tool is an action the model chooses; a
resource is content addressed by URI that the client fetches directly.

**Path traversal matters more here.** `../../.env` targets the file holding the
API key, and it was blocked, along with the backslash variant. Resolve first,
then check containment - scanning for `..` before resolving misses symlinks and
absolute paths.

**Two version problems.** `mcp` 2.0 breaks `langchain-mcp-adapters`, which imports
a symbol 2.0 removed, so it is pinned below 2.0. And MCP is async throughout, so
calling the sync fallback helper raised `asyncio.run() cannot be called from a
running event loop`. You cannot bridge into a running loop from inside it, which
is why `arun_with_fallback` exists.

---

## Module 15 - Production AI

**Folder:** [`15-Production-AI/`](15-Production-AI/) - [README](15-Production-AI/README.md)

| File | Purpose |
|------|---------|
| `app.py` | The API. Four endpoints. |
| `test_api.py` | 14 free checks, 3 more with `--live` |
| `Dockerfile` | Container build |
| `requirements-api.txt` | Only what the API imports |

**Topics:** FastAPI, streaming, logging, authentication, Docker, LangSmith.

### How it works

| Endpoint | Auth | Model call |
|----------|------|-----------|
| `GET /health` | no | **no** |
| `GET /config` | yes | no |
| `POST /chat` | yes | yes |
| `POST /chat/stream` | yes | yes |

### Why it is built this way

`TestClient` runs the app in process, so auth, validation, error mapping and
logging are all testable without a port or a model call. That is where most
service bugs live.

### What I learned

**A health check must not call the model.** A load balancer polling every few
seconds would exhaust the free quota by itself, and would report the service
unhealthy for a reason unrelated to whether it is running.

**Mapping provider errors to HTTP codes is the difference between an API and a
wrapper.** Quota exhausted becomes 429 with `Retry-After`, not 500. A client
seeing 429 backs off; a client seeing 500 retries immediately and makes it worse.
The classification functions came unchanged from `common/errors.py`, written in
Module 01 for friendlier console messages.

**Log in full, return sanitised.** A Gemini 429 contains project ids and quota
internals that do not belong in a response body.

**The service key is not the provider key.** The Gemini key never leaves the
server, and a test asserts no response contains `AIza`.

**Streaming changes error handling.** Once the first chunk is sent the status is
already 200, so a later failure has to be reported inside the stream. A client
checking only the status code would treat a failed stream as success.

**Ship only what you import.** My first Dockerfile installed the whole
`requirements.txt` - chromadb, FAISS, a reranker, PDF parsers - none of which the
API imports. `requirements-api.txt` has five entries, verified by installing it
into a clean environment and importing the app.

**Not everything got verified.** The Docker image was never built, because the
Docker daemon was not running. That is recorded rather than glossed over.

---

## Lessons that run through the whole course

**Do not trust a number because of what it is called.** Module 06 found that
"unrelated" text scores 0.75. Module 07 found `similarity_search_with_score`
returns a distance where lower is better, and that the official "relevance score"
helper can go negative. Sorting by either the obvious way gives you the worst
results first.

**Measure instead of repeating advice.** Three standard claims did not survive
testing: grounding prompts did not prevent hallucination, reranking made
retrieval worse, and summary memory cost more than it saved. All three are
defensible in the right context, and none is a rule.

**Cost is a design constraint, not an afterthought.** A 20 request daily limit
forced offline modes into almost every module - `--show-prompt`, `show`,
`--dry-run`, `stats`, `tools`. Those turned out to be the best debugging tools
anyway, because they isolate the part that usually breaks.

**The failure you can see is rarely the cause.** A JSON parse error was a 403
about a User-Agent. An import error naming Databricks was auto-detection. A
truncated joke was reasoning tokens. Read the whole error, and reproduce it in
isolation.

**Descriptions written for models are code.** Pydantic field descriptions, tool
docstrings, `AttributeInfo` text - all are sent with every request. They are
prompt engineering that happens to live in a docstring.

**Untrusted input arrives from the model.** Anything a model fills in may be
echoing a user. Both places it mattered - the calculator and the file server -
are guarded structurally rather than by blocklist.

**Verify by running it.** Every finding in these READMEs is measured output.
Several came from the code being wrong the first time.

---

## Where the original plan was wrong

The guide was drafted before any of this was built. Most of the corrections come
from the ecosystem moving, not from the plan being careless.

| Planned | Reality | Where |
|---------|---------|-------|
| `langchain.retrievers` | Moved to `langchain_classic` | 09 |
| `langchain.memory`, `ConversationChain` | Gone from 1.x, deprecated in classic | 12 |
| `AgentExecutor`, `create_react_agent` | Replaced by `create_agent` | 11 |
| `wikipedia` package | Broken, Wikipedia now needs a User-Agent | 11 |
| A weather API key | Not needed, Open-Meteo is free and keyless | 11 |
| Cohere Rerank | Replaced with a local cross encoder, no account | 10 |
| `sentence-transformers` | 2 GB of PyTorch, replaced by `flashrank` at 0.1 MB | 10 |
| Latest `mcp` | Breaks the LangChain adapter, pinned below 2.0 | 14 |
| `gemini-2.0-flash` | No free tier quota at all | 01 |
| "Module 04 costs four calls" | Three model steps, so three calls | 04 |

The guide has been updated to match, with each change noted where it applies.
