# Module 06 - Embeddings

**Status:** complete. All four modes run against the live API.

## Goal

Turn text into vectors, compare those vectors, and understand what the numbers
do and do not mean.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| Embeddings | `embed` |
| Cosine similarity | `cosine_similarity`, written by hand |
| Semantic search | `--mode search` |
| Normalisation | `normalise` |
| task_type | `--mode search` |

## Files

| File | Purpose |
|------|---------|
| `similarity_checker.py` | The mini project. Four modes. |
| `sample_sentences.txt` | Ten sentences including deliberate homonyms. |

## Running it

```powershell
python similarity_checker.py --mode demo
python similarity_checker.py --mode pair "a cat sat on the mat" "a feline rested on the rug"
python similarity_checker.py --mode search --query "borrowing money from a bank" --top 5
python similarity_checker.py --mode matrix --width 45
```

| Flag | Meaning |
|------|---------|
| `--mode` | `demo`, `pair`, `search` or `matrix`. Default `demo`. |
| `--query` | search query, required for `search` |
| `--file` | sentences file, default `sample_sentences.txt` |
| `--top` | results to show, default 5 |
| `--width` | sentence width in the matrix legend |
| `--debug` | show the full traceback |

**Cost:** one API call per run, because every mode embeds all its text in a
single batched request. `search` costs two, since query and documents are
embedded separately. Embeddings have their own quota, separate from the chat
models, so this module does not eat into the earlier ones.

## What you should see

### demo

```
model: models/gemini-embedding-001, dimensions: 3072
12 sentences embedded in a single request

1.0000  near identical  identical text
0.8954  same meaning    same meaning, no shared words
          a: The bank approved my loan application.
          b: My mortgage was accepted by the lender.
0.8362  related         related topic
0.7817  weakly related  shared word, different meaning
          a: The bank approved my loan application.
          b: I sat on the river bank watching the water.
0.7697  weakly related  shared word, different meaning
0.7488  unrelated       unrelated
```

**The ordering is the thing to check.** The pair with the same meaning and
almost no shared vocabulary (0.895) must outrank both pairs that share a word
but mean different things (0.78, 0.77). That gap is the entire reason
embeddings beat keyword matching: a keyword search would rank those the other
way round.

Your numbers should be within a few thousandths of these.

### search

```
query: borrowing money from a financial institution

0.6666  The bank approved my loan application last week.
0.6249  My mortgage was accepted by the lender a few days ago.
0.5892  The weather forecast says it will rain tomorrow.
0.5833  She trained a model to predict tomorrow's rainfall.
0.5830  The server crashed under heavy load last night.
0.5826  I sat on the river bank and watched the water go by.
...
0.5720  The waiter brought our food to the wrong table.
```

Three things here:

**The top two are right and contain none of the query's words.** No
"borrowing", no "financial", no "institution". That is semantic search working.

**There is a cliff, then a flat floor.** 0.667 and 0.625 stand clearly apart,
then everything from rank three down sits between 0.572 and 0.589. That flat
region is noise, not weak relevance. **Look for the gap, not a threshold** -
this is how to choose a sensible `top_k` in the retrieval modules.

**The river bank sentence ranks sixth.** It shares the concept "bank" with the
query's subject matter but not its meaning, and the model placed it in the
noise. That is homonym disambiguation working.

### matrix

```
           0      1      2      3      4      5      6      7      8      9
  0    1.000  0.788  0.859  0.710  ...
  ...
closest pair: 5 and 6 at 0.8761
```

Worth reading closely:

| Pair | Score | Why it matters |
|------|-------|----------------|
| 5 and 6 (rainfall model / rain forecast) | 0.876 | highest, and correct |
| 0 and 2 (loan approved / mortgage accepted) | 0.859 | paraphrase, no shared words |
| 0 and 1 (bank loan / river bank) | 0.788 | same word, lower score |
| 3 and 4 (Python language / python snake) | 0.717 | near the bottom of the matrix |

The last row is the clearest single result in this module. Two sentences share
their most distinctive word and are still pushed apart, because the surrounding
context disambiguates them.

## Things worth knowing

### Absolute similarity scores are close to meaningless

This is the most useful thing in the module, and most tutorials get it wrong.

Textbook explanations say cosine similarity runs from -1 to 1, where 0 means
unrelated. With `gemini-embedding-001` that is simply not what happens. Measured
here:

| Comparison | Score |
|------------|-------|
| identical text | 1.000 |
| completely unrelated sentences | **0.749** |

**Nothing observed fell below 0.7.** A tutorial rule like "similar means above
0.5" would mark every pair in this module as a strong match, including the
unrelated one.

Worse, the range moves with `task_type`. The same model scored 0.75 to 1.00 in
`demo` and 0.57 to 0.67 in `search`, purely because the search mode tags query
and documents differently.

So:

- **Rank, do not threshold.** Ordering is reliable; the raw number is not.
- If you must have a cut off, **calibrate it** against pairs whose answer you
  already know, for your model and your `task_type`.
- The thresholds in `label_for` are calibrated to this model from the measured
  numbers above, and are documented as such rather than presented as universal.

### Truncated vectors are not unit length

`gemini-embedding-001` returns 3072 dimensions by default. Setting
`GEMINI_EMBEDDING_DIM` truncates them, which saves storage in the vector
database modules. Measured L2 norms:

| Dimensions | L2 norm |
|-----------|---------|
| 3072 (default) | 1.000000 |
| 1536 | 0.693384 |
| 768 | 0.577804 |

**Only the full size vectors come back normalised.** Cosine similarity divides
by both norms so it survives either way, but a plain dot product does not, and
most vector databases use dot product for speed on the assumption that vectors
are unit length.

`normalise` is therefore applied to every vector after embedding. It is a no-op
at 3072 and a correctness fix at any smaller size. This is the kind of bug that
does not crash, it just quietly returns worse results.

### task_type changes the vector

Gemini produces a different vector for the same text depending on what it is
for:

```python
document_vectors = embed(sentences, task_type="RETRIEVAL_DOCUMENT")
query_vector = embed([query], task_type="RETRIEVAL_QUERY")[0]
```

A question and the passage that answers it are not paraphrases of each other,
so embedding both the same way is a poor fit for search. Using the pair costs
one extra call and measurably improves ranking. `SEMANTIC_SIMILARITY` exists for
comparing two texts as equals, which is what `demo` and `matrix` do by leaving
it unset.

### Batching is what keeps this cheap

`embed_documents` sends the whole list in one request. Twelve sentences in
`demo` cost one call, not twelve. Cost scales with the number of requests, not
the amount of text, so **always batch**. This matters a great deal in the vector
database modules, where a few thousand chunks are embedded at once.

### Cosine, not euclidean

`cosine_similarity` is written out rather than imported:

```python
float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

It measures the angle between vectors and ignores their length. For text
embeddings, direction carries the meaning and length carries very little, which
is why cosine is the standard choice. For unit length vectors it reduces to the
dot product, which is why normalising is worth doing once up front.


