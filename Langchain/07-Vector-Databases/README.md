# Module 07 - Vector Databases

**Status:** complete. All four commands run against the live API.

## Goal

Store embeddings so they can be searched repeatedly without re-embedding, and
understand what the returned scores actually mean.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| Chroma | `build`, `search` |
| FAISS | `compare` |
| Metadata | `parse_notes`, `--category` |
| Similarity search | `search` |
| Persistence | `build` then `search` |

## Files

| File | Purpose |
|------|---------|
| `notes_search.py` | The mini project. Four commands. |
| `sample_notes.txt` | Ten notes across three categories. |

Generated at build time, both gitignored:

| Directory | Contents |
|-----------|----------|
| `chroma_db/` | Chroma's SQLite database and index |
| `faiss_index/` | `index.faiss` and `index.pkl` |

## Setup

```powershell
pip install -r ..\requirements.txt
python notes_search.py build
```

## Running it

```powershell
python notes_search.py build --rebuild
python notes_search.py stats
python notes_search.py search --query "why was the service slow under traffic"
python notes_search.py search --query "service" --category personal
python notes_search.py compare --query "how big should chunks be"
```

| Command | Cost |
|---------|------|
| `build` | one call, every note embedded in one batch |
| `search` | one call, to embed the query |
| `compare` | two calls, one per store |
| `stats` | none |

**That split is the whole point of a vector database.** Module 06 re-embedded
everything on every run. Here the notes are embedded once and stored, so a
search only has to embed the query. With a real corpus that is the difference
between a usable system and an unaffordable one.

## What you should see

### build

```
parsed 10 notes from sample_notes.txt
chroma:  wrote 10 vectors to chroma_db/
faiss:   wrote 10 vectors to faiss_index/
```

### stats

```
collection: notes
vectors:    10

by category
  personal   3
  study      3
  work       4

no API call was made. metadata is stored alongside the vectors.
```

### search

```
query:    why was the service slow under traffic

   score  similarity  category   title
  0.2973      0.7027  work       Postgres connection pool
  0.3347      0.6653  personal   Bike service
  0.3870      0.6130  study      Token limits
  0.3886      0.6114  personal   Bread recipe
```

**The top hit is right.** The query shares almost no wording with the note,
which is about a connection pool being set too low. It was retrieved on
meaning.

**The second hit is a genuine false positive**, and worth studying. "Bike
service" matched because of the word "service", which means something entirely
different here. Compare this with the scores: 0.297 for the real answer, then
0.335, 0.387, 0.389 bunched together. The same cliff-then-flat-floor pattern
from Module 06. Everything after the first result is noise.

This is exactly why Module 10 exists: pure semantic search has failure modes,
and reranking is how they get fixed.

### compare

```
chroma (cosine distance, lower is better)
    0.2391  Chunk overlap
    0.3424  Token limits
    0.3724  Postgres connection pool

faiss (squared euclidean distance, lower is better)
    0.4782  Chunk overlap
    0.6849  Token limits
    0.7447  Postgres connection pool

same ranking: True
```

Look at the numbers: FAISS returns **exactly double** Chroma's. Same ranking,
different scale. For unit length vectors, squared euclidean distance is
`2 x cosine distance`, so the two agree on order while disagreeing on every
number. Neither store is finding better matches than the other here.

## The thing most likely to trip you up

**`similarity_search_with_score` does not return a similarity.** It returns a
**distance**, where lower is better.

Measured with a controlled fake embedder, querying for a vector whose true
cosine similarity to each document is known:

| True cosine similarity | Chroma score returned |
|------------------------|-----------------------|
| 1.00 (identical) | **0.00** |
| 0.90 (very close) | **0.20** |
| 0.00 (orthogonal) | **2.00** |

The relationship under the default `l2` space is `score = 2 - 2 x cosine`. The
best possible match scores zero.

**Sorting results by this "score" in descending order gives you the worst
matches first**, and the code looks perfectly reasonable while doing it. This
follows directly from Module 06's lesson: do not trust a number because of what
it is called.

Two ways to make it readable, both used here:

**Set the distance function explicitly.** Building with
`collection_metadata={"hnsw:space": "cosine"}` makes the score a cosine
distance, so `similarity = 1 - score`, which is easy to reason about. Same
controlled test under cosine space returned 0.0, 0.1 and 1.0.

**Print both.** The `search` output shows the raw score and the converted
similarity side by side, so the direction is never ambiguous.

### The relevance score helper is not a fix

LangChain offers `similarity_search_with_relevance_scores`, which claims to
normalise to a 0 to 1 range. On the same controlled test it returned:

| True cosine similarity | Relevance score |
|------------------------|-----------------|
| 1.00 | 1.0000 |
| 0.90 | 0.8586 |
| 0.00 | **-0.4142** |

The bottom value is negative, outside the range it advertises. It is derived
from the distance with a fixed formula rather than measured, so it inherits the
same assumptions. Useful for ranking, still not safe to threshold.

## Things worth knowing

### Metadata has to exist before you store

`parse_notes` attaches `category` and `title` when the note is read, because
filtering happens inside the database. Adding a field later means rebuilding
the store.

The filter is applied during the search, not afterwards:

```python
store.similarity_search_with_score(query, k=top, filter={"category": "personal"})
```

That matters. Retrieving four results and then discarding the ones in the wrong
category would often leave you with fewer than four, or none. Filtering inside
the database narrows the candidates first, then ranks what is left. Try
`--category personal` with a work-flavoured query and you still get three
personal notes back.

### FAISS needs allow_dangerous_deserialization

```python
FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)
```

Without it, loading raises. A FAISS store is restored with `pickle`, which can
execute arbitrary code, so LangChain forces you to acknowledge it. Fine for a
file this script just wrote. **Never set it on a store downloaded from
somewhere else** - it is equivalent to running a stranger's Python.

Chroma has no such flag because it stores to SQLite rather than pickle.

### Chroma or FAISS

| | Chroma | FAISS |
|---|--------|-------|
| Package | `langchain-chroma`, maintained | `langchain-community`, being sunset |
| Storage | SQLite directory, persists itself | two files, saved explicitly |
| Metadata filtering | built in | limited |
| Speed at scale | good | excellent, it is a specialised library |

Chroma is the default here: it is in a maintained package, it filters on
metadata properly, and it persists without an explicit save step. FAISS is
included for the comparison and because it appears constantly in tutorials.

### The store needs the model, not the vectors

Module 06 embedded text and compared vectors by hand. A vector store calls
`embed_documents` and `embed_query` itself, so it needs the embedding model
object. That is why this module uses `build_embeddings` directly rather than
the `embed_with_fallback` wrapper: the fallback wraps a call, and here the call
happens inside the database.

The consequence is that this module does not automatically rotate models when
quota runs out. If a build fails on quota, change `GEMINI_EMBEDDING_MODEL` in
`.env` by hand.

### task_type differs between build and search

`build` uses `RETRIEVAL_DOCUMENT`, `search` uses `RETRIEVAL_QUERY`. The stored
vectors and the query vector are produced by different settings on purpose, for
the reasons in Module 06. Rebuilding with the wrong one degrades results quietly
rather than failing.


## A vector store always returns k results

Worth its own section, because it causes real bugs in RAG.

```powershell
python notes_search.py search --query "booking a flight to Tokyo" --top 3
```

```
   score  similarity  category   title
  0.4437      0.5563  study      Token limits
  0.4489      0.5511  personal   Dentist
  0.4547      0.5453  personal   Bike service
```

Nothing in these notes is remotely about flights. The store returned three
results anyway, confidently, with a similarity above 0.54. **A vector store has
no concept of "no good match".** Ask for k, get k.

Two signals that these are junk, and neither is the score on its own:

- **The scores are flat.** 0.4437, 0.4489, 0.4547, a spread of one hundredth.
  A real match produces a visible gap, as in the connection pool search where
  the top hit stood 0.04 clear of second place.
- **They are worse than every earlier query's top hit**, which ranged from 0.24
  to 0.30.

Also enjoy the top result: **"Token limits" matched "Tokyo"**. The embedding
picked up on surface form, not meaning, which is precisely the failure
embeddings are supposed to avoid.

In a RAG pipeline this is dangerous, because these three notes would be passed
to a model as context for a question about flights, and the model will do
something with them. Module 08 covers telling the model it is allowed to say it
does not know. Module 10 covers filtering results like this out before they get
that far.
