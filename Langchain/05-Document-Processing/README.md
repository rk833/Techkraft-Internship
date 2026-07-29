# Module 05 - Document Processing

**Status:** complete. Runs entirely offline.

## Goal

Load documents of different types and see exactly how they are split into
chunks, since chunking quality decides how well every later retrieval module
works.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| PDF loader | `load`, via `PyPDFLoader` |
| DOCX loader | `load_docx`, hand written |
| TXT loader | `load`, via `TextLoader` |
| RecursiveCharacterTextSplitter | `--splitter recursive`, the default |
| CharacterTextSplitter | `--splitter character` |
| TokenTextSplitter | `--splitter token` |
| Metadata | printed per chunk |

## Files

| File | Purpose |
|------|---------|
| `chunk_viewer.py` | The mini project. Loads a document and shows its chunks. |
| `make_samples.py` | Generates `sample.txt`, `sample.docx` and `sample.pdf`. |

## Setup

This module needs packages the earlier ones did not:

```powershell
pip install -r ..\requirements.txt
python make_samples.py
```

`make_samples.py` writes the same text as three file types, so the same content
can be loaded three ways and the differences compared.

## Running it

```powershell
python chunk_viewer.py sample.pdf
python chunk_viewer.py sample.pdf --chunk-size 400 --chunk-overlap 80 --show-overlap
python chunk_viewer.py sample.txt --splitter character
python chunk_viewer.py sample.pdf --compare
python chunk_viewer.py "C:\path\to\your\own.pdf" --stats-only
```

| Flag | Meaning |
|------|---------|
| `--chunk-size` | target chunk size, default 500 |
| `--chunk-overlap` | characters repeated between chunks, default 100 |
| `--splitter` | `recursive`, `character` or `token` |
| `--show-overlap` | show the text actually shared between neighbours |
| `--compare` | run all three splitters and compare |
| `--stats-only` | skip the per chunk listing |
| `--preview-width` | characters shown per chunk, default 90 |

**No API calls.** Nothing here costs quota, so experiment as much as you like.

## What you should see

```powershell
python chunk_viewer.py sample.pdf --chunk-size 400 --chunk-overlap 80 --show-overlap
```

```
loaded 2 document(s) from sample.pdf
metadata of first: {'producer': 'PyPDF', ..., 'total_pages': 2, 'page': 0, 'page_label': '1'}

splitter=recursive chunk_size=400 chunk_overlap=80

[  0] chars=332   tokens=73    page=1
      Chunking and why it matters\nA language model can only read so much text...
      overlap with next: 70 chars: surrounding context together, which helps the model...

[  1] chars=388   tokens=82    page=1
      surrounding context together, which helps the model understand what it\nis...
      overlap with next: none

[  2] chars=332   tokens=73    page=2
      Overlap\nOverlap repeats the end of one chunk at the start of the next...
      overlap with next: 69 chars: of the chunk size. Too little and boundaries stay...

[  3] chars=379   tokens=77    page=2
      of the chunk size. Too little and boundaries stay sharp; too much and...

stats
  documents loaded:  2
  original chars:    1292
  chunks produced:   4
  chunk chars:       min 332, avg 357, max 388
  repeated by overlap: 139 chars (10.8% more than the original)
```

Four things to look at:

**Two documents from one PDF.** `PyPDFLoader` returns one `Document` per page
before any chunking happens, and records `page` and `page_label` in metadata.

**`overlap with next: none` between chunks 1 and 2.** That is not a bug. Chunks
1 and 2 come from different pages, and splitting happens per document, so no
overlap is ever created across a page boundary. Anything split across a page
break loses its context, which is a real limitation of loading PDFs page by
page.

**Every chunk is under 400 characters.** The recursive splitter found sensible
break points.

**Overlap costs storage.** 10.8 percent more text than the original, and every
repeated character is embedded and stored again in later modules.

Exact numbers depend on the flags, but chunk count and page attribution should
match.

## Comparing the splitters

```powershell
python chunk_viewer.py sample.pdf --compare --chunk-size 400 --chunk-overlap 80
```

```
splitter      chunks  min ch  avg ch  max ch  avg tok
recursive          4     332     357     388       76
character          2     642     646     650      138
token              2     642     646     650      138
```

This one table contains most of the module.

### RecursiveCharacterTextSplitter

Tries a list of separators in order: `["\n\n", "\n", " ", ""]`. Paragraph break
first, then line break, then space, then anywhere. It only falls back to a
cruder cut when a finer one will not fit.

Result: four chunks, all within the 400 limit. **This is the right default.**

### CharacterTextSplitter

Splits on one separator only, here a blank line. Text extracted from a PDF has
no blank lines, so there is nothing to split on, and it returns chunks of 642
and 650 characters against a limit of 400.

Run it directly and the stats say so:

```
over chunk_size:   2 chunk(s), largest 650
                   a chunk can exceed the limit when no separator fits
```

**`chunk_size` is a target, not a guarantee.** A splitter that cannot find an
acceptable break point will hand back an oversized chunk rather than cut mid
word. Anything downstream with a hard context limit has to cope with that.

Try the same comparison on `sample.txt`, which does have blank lines: there
`character` and `recursive` agree exactly. The splitter is not bad, it is
sensitive to the document, and PDF text is exactly the case where it fails.

### TokenTextSplitter

Counts tokens rather than characters. `chunk_size=400` means 400 tokens, which
is roughly 1600 characters, so it barely splits the sample at all.

That is the point: **the same number means different things per splitter.** A
model's context limit is measured in tokens, so token splitting maps directly
onto what actually constrains you. Character splitting is easier to reason
about but only approximates the real limit.

## Choosing chunk size and overlap

There is no correct answer, only a trade off:

- **Large chunks** keep context together, but retrieve poorly. A chunk covering
  six topics matches weakly against a question about any one of them.
- **Small chunks** retrieve precisely, but can strand a fact away from the
  paragraph that explained it.
- **Overlap** softens boundaries. Ten to twenty percent of chunk size is a
  common starting point. The `repeated by overlap` stat shows what it costs.

Try `--chunk-size 150` and then `--chunk-size 1000` on the same file and read
the chunks. That comparison is worth more than any rule of thumb.

## Things worth knowing

### langchain-community is being sunset

`PyPDFLoader` and `TextLoader` live in `langchain_community`, which now warns on
import that it is no longer actively maintained. There is currently no
standalone replacement package for the PDF loader, so it is still used here,
with the warning suppressed around the import.

This is worth watching. If it is eventually removed, the fix is small, which the
next point demonstrates.

### A loader is not magic

`Docx2txtLoader` needs a separate `docx2txt` package, which `python-docx` is
not. Rather than add another dependency, `load_docx` is written by hand:

```python
document = DocxFile(path)
text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
return [Document(page_content=text, metadata={"source": str(path)})]
```

That is the entire contract. **A loader is anything that returns `Document`
objects with `page_content` and `metadata`.** Once that is clear, being tied to
a deprecated package stops being frightening, and loading from a database, an
API or a scraped page is obviously within reach.

### Token counts are approximate

`count_tokens` uses `tiktoken`, which is OpenAI's tokenizer, not Gemini's. Close
enough to reason about chunk sizes, but not exact. An exact count needs the
provider's own `count_tokens` call, which costs a request.

### Overlap is recovered, not reported

Splitters do not report the overlap they produced, so `find_overlap` recovers it
by comparing the end of one chunk with the start of the next. Worth doing
because the real overlap is often smaller than requested: the splitter honours
separator boundaries first and the overlap setting second.

### The sample PDF is hand written

`make_samples.py` builds `sample.pdf` by writing PDF syntax directly, rather
than pulling in a PDF library just to create a fixture. A PDF is a text
container of numbered objects plus a table of byte offsets, and seeing that
makes it clearer why extracted text so often arrives with awkward line breaks
and no paragraph structure.

