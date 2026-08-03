# 02 - Routing and APIRouter

## What This Project Does

A book catalogue API with two resources, books and authors, backed by an in-memory dict. It covers
every common HTTP method and splits the routes across separate files with `APIRouter` instead of
piling them into `main.py`.

The subject is organisation and HTTP method semantics. Data validation is deliberately absent -
that is module 04, and this project is built to make the need for it obvious.

## Topics Covered

- GET, POST, PUT, PATCH, DELETE and what each actually means
- Route decorators and path design
- `APIRouter` for splitting routes across files
- Router-level prefixes and tags
- Route ordering, and why `/books/featured` must be declared before `/books/{book_id}`
- Nested resource paths (`/authors/{id}/books`)
- 201 Created and 204 No Content

## Project Layout

```
02-routing/
|-- main.py              app creation and router registration, nothing else
|-- data.py              in-memory store
|-- routers/
    |-- __init__.py
    |-- books.py         7 routes
    |-- authors.py       4 routes
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

## Endpoints

| Method | Path | Description | Success |
|--------|------|-------------|---------|
| GET | `/books` | List all books | 200 |
| GET | `/books/featured` | List featured books only | 200 |
| GET | `/books/{book_id}` | Get one book | 200 |
| POST | `/books` | Add a book | 201 |
| PUT | `/books/{book_id}` | Replace a book entirely | 200 |
| PATCH | `/books/{book_id}` | Update some fields of a book | 200 |
| DELETE | `/books/{book_id}` | Delete a book | 204 |
| GET | `/authors` | List all authors | 200 |
| GET | `/authors/{author_id}` | Get one author | 200 |
| GET | `/authors/{author_id}/books` | List that author's books | 200 |
| POST | `/authors` | Add an author | 201 |
| GET | `/health` | Service health check | 200 |

## How It Works

### APIRouter

`APIRouter` collects routes without needing an application to attach them to. Each resource declares
one:

```python
router = APIRouter(prefix="/books", tags=["books"])
```

The prefix and tag are set once, so no route below repeats `/books` in its path or `tags=` in its
decorator. `main.py` then mounts them:

```python
app.include_router(books.router)
app.include_router(authors.router)
```

The result is that `main.py` stays at roughly twenty lines regardless of how many resources exist.
Adding one means adding a file and a single line here. That property is the whole reason routers
exist, and it is why module 11 onward stays navigable.

### Route ordering

FastAPI matches routes in declaration order and stops at the first hit. So this ordering matters:

```python
@router.get("/featured")     # declared first
@router.get("/{book_id}")    # declared second
```

Reversed, `/books/{book_id}` would match the literal request `GET /books/featured`, try to coerce
the string `"featured"` into the `int` parameter, fail, and return 422. The `/featured` route would
still exist and still appear in the docs, but would be permanently unreachable.

I built a deliberately reversed router to confirm this rather than take it on trust:

```
wrong order  GET /books/featured -> 422 Input should be a valid integer, unable to parse string as an integer
```

The rule: static path segments before dynamic ones.

### PUT vs PATCH

Both update, and the difference is not cosmetic:

- **PUT** replaces the whole resource. Any field the client omits is reset to its default, not kept.
  It is idempotent - sending it twice leaves the same state as sending it once.
- **PATCH** merges only the fields present in the payload. Everything else is untouched.

Visible in the run below: `PUT` with no `featured` field reset it to `false`, then `PATCH` with only
`{"featured": true}` set it back without disturbing the title or year.

### Status codes

`POST` returns **201 Created**, not 200, because a new resource now exists.

`DELETE` returns **204 No Content** and the function returns `None`. 204 means "success, and there
is deliberately no body". Returning data alongside a 204 violates the protocol, and FastAPI enforces
this - the response body is empty in the run output below.

## Why It Is Done This Way

**Why `main.py` contains no endpoints except `/health`.** Its job is composition: create the app,
register the routers. Putting business routes there mixes two concerns and is the habit that
produces 800-line `main.py` files. `/health` is the one justified exception, because it belongs to
the application rather than to any resource.

**Why the payload is an untyped `dict`.** `POST /books` accepts `payload: dict`, which means it
accepts absolutely anything. This is bad code and it is intentional. Proven in the run below:

```
POST /books {"title": 12345, "author_id": "not-a-number", "year": "banana"} -> 201
```

A title that is a number and a year that is a fruit were accepted and stored. Swagger UI also shows
no request schema for this endpoint, because there is no type information to generate one from.
Module 04 replaces the dict with a Pydantic model, and having felt the gap first makes that change
land as a fix rather than as ceremony.

**Why `/authors/{id}/books` rather than `/books?author_id=1`.** Both are defensible. The nested form
expresses containment - these books belong to this author - and gives a natural place for an author
404. The query-parameter form is better once filtering gets complex, which is exactly what module 03
builds.

**Why 404 for an unknown author's books rather than an empty list.** "This author does not exist"
and "this author has written nothing" are different answers. Collapsing them into `[]` hides typos
and broken IDs from the client.

**Why `data.py` is a module-level dict.** It is not thread-safe and it vanishes on restart. Both are
acceptable here and neither is acceptable later; module 11 replaces it with SQLAlchemy.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8. Every endpoint, both happy and failure paths:

```
--- read ---
GET    /health                      -> 200  {"status":"ok","version":"0.1.0"}
GET    /books                       -> 200  [4 books]
GET    /books/featured              -> 200  [2 books]
GET    /books/1                     -> 200  {"id":1,"title":"A Wizard of Earthsea",...}
GET    /books/999                   -> 404  {"detail":"No book with id 999"}
GET    /authors                     -> 200  [3 authors]
GET    /authors/1/books             -> 200  [2 books]
GET    /authors/99/books            -> 404  {"detail":"No author with id 99"}

--- write ---
POST   /books                       -> 201  {"id":5,"title":"The Left Hand of Darkness","author_id":1,"year":1969,"featured":false}
PUT    /books/5                     -> 200  {"id":5,"title":"Replaced","author_id":1,"year":2000,"featured":false}
PATCH  /books/5                     -> 200  {"id":5,"title":"Replaced","author_id":1,"year":2000,"featured":true}
DELETE /books/5                     -> 204  (no body)
GET    /books/5                     -> 404  {"detail":"No book with id 5"}
DELETE /books/999                   -> 404  {"detail":"No book with id 999"}

--- validation gap, fixed in module 04 ---
POST   /books  {"title":12345,"author_id":"not-a-number","year":"banana"}
                                    -> 201  accepted and stored

--- route ordering ---
declared order: featured at index 1, {book_id} at index 2 -> correct: True
reversed router: GET /books/featured -> 422 "Input should be a valid integer"

--- tags ---
GET/POST/PUT/PATCH/DELETE  /books*     tags=['books']
GET/POST                   /authors*   tags=['authors']
GET                        /health     tags=['general']
```

## What I Learned

- A router carries its prefix into its own `routes` list, so inspecting `books.router.routes` shows
  full paths like `/books/featured`, not the `/featured` written in the decorator.
- Route shadowing is the nastiest bug in this module, because nothing warns you. The shadowed route
  still renders in Swagger UI and still looks correct in the source. It just never runs. The 422
  about parsing an integer is the only clue, and it points at the wrong route.
- `app.routes` no longer contains included routes flatly - this version of FastAPI wraps each
  included router in an `_IncludedRouter` object, so a naive loop over `app.routes` finds only
  `/health` and the docs routes. This surfaced while writing the verification, and the router had to
  be inspected directly instead.
- PATCH taking two lines more than PUT while being the safer default was not obvious. Most real
  update endpoints want PATCH semantics.
- Accepting `payload: dict` and watching `"year": "banana"` get stored makes the point of Pydantic
  clearer than reading about validation would.


## Navigation

[Previous](../01-hello-fastapi/) | [All modules](../README.md) | [Next](../03-path-and-query-parameters/)
