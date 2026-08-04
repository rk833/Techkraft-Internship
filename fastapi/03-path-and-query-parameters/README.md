# 03 - Path and Query Parameters

## What This Project Does

A product search API over a 12-item catalogue. One endpoint accepts eleven optional query
parameters covering text search, category, price range, rating, stock, tags, sorting and
pagination. A second endpoint fetches one product by a validated path parameter.

The point is that almost none of the validation is written as code. It is declared in the function
signature, and FastAPI rejects bad input with a 422 before the function body runs.

## Topics Covered

- Path parameters and type coercion
- Query parameters, defaults, and optional values
- `Path()` and `Query()` constraints: `ge`, `le`, `min_length`, `max_length`
- `Annotated[...]` as the current way to attach parameter metadata
- Enums as parameter types for fixed choices
- List query parameters
- Pagination with `limit` and `offset`, and why `total` is returned separately
- What FastAPI cannot validate from a signature, and why module 05 exists

## Project Layout

```
03-path-and-query-parameters/
|-- main.py                  app creation and router registration
|-- data.py                  12 products, plus the Category enum
|-- routers/
    |-- __init__.py
    |-- products.py          search, get-one, list-categories
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

Swagger renders every constraint below as a real form control - a dropdown for the enums, a number
box with min and max for the bounded integers. Worth looking at, because it is generated entirely
from the signature.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/products` | Search, filter, sort and paginate the catalogue |
| GET | `/products/categories` | List the accepted category values |
| GET | `/products/{product_id}` | Get one product |
| GET | `/health` | Service health check |

### Search parameters

| Parameter | Type | Constraint | Default |
|-----------|------|------------|---------|
| `q` | string | 2 to 50 characters | none |
| `category` | enum | audio, wearables, peripherals, storage | none |
| `min_price` | float | `>= 0` | none |
| `max_price` | float | `>= 0` | none |
| `min_rating` | float | `0` to `5` | none |
| `in_stock` | bool | | none |
| `tags` | list of string | repeat the parameter per tag, all must match | none |
| `sort_by` | enum | name, price, rating | `name` |
| `order` | enum | asc, desc | `asc` |
| `limit` | int | `1` to `100` | `20` |
| `offset` | int | `>= 0` | `0` |

## How It Works

### Annotated, not the old default-value style

```python
q: Annotated[str | None, Query(min_length=2, max_length=50)] = None
```

The older form, `q: str | None = Query(None, min_length=2)`, still works but puts the default inside
`Query()` where a reader expects to find it after the `=`. `Annotated` keeps the type, the metadata
and the default in three distinct places. It is the form the FastAPI docs now use.

### The signature is the validation

Nothing in `search_products` checks a type or a range. Every one of these 422s came from the
signature alone:

```
422  ?limit=0             ['query','limit']      Input should be greater than or equal to 1
422  ?limit=500           ['query','limit']      Input should be less than or equal to 100
422  ?offset=-1           ['query','offset']     Input should be greater than or equal to 0
422  ?min_rating=9        ['query','min_rating'] Input should be less than or equal to 5
422  ?min_price=-5        ['query','min_price']  Input should be greater than or equal to 0
422  ?q=a                 ['query','q']          String should have at least 2 characters
422  ?category=furniture  ['query','category']   Input should be 'audio', 'wearables', 'peripherals' or 'storage'
422  ?sort_by=colour      ['query','sort_by']    Input should be 'name', 'price' or 'rating'
422  ?limit=abc           ['query','limit']      Input should be a valid integer
```

The `loc` field names the exact parameter that failed, which is why a client can point at the right
input box without any error-mapping code on our side.

### Enums

`Category(str, Enum)` does three jobs at once. It restricts the accepted values, it produces the
error message listing the valid options, and it becomes a dropdown in Swagger UI. Inheriting from
`str` as well as `Enum` is what lets the plain string `"audio"` arrive from a query string and
serialise back out as `"audio"` rather than `Category.AUDIO`.

Confirmed in the generated schema:

```
q           {'type':'string','minLength':2,'maxLength':50}                  default=None
category    {'type':'string','enum':['audio','wearables','peripherals','storage']}
min_rating  {'type':'number','maximum':5,'minimum':0}                       default=None
tags        {'type':'array','items':{'type':'string'}}                      default=None
sort_by     {'type':'string','enum':['name','price','rating']}              default=name
order       {'type':'string','enum':['asc','desc']}                         default=asc
limit       {'type':'integer','maximum':100,'minimum':1}                    default=20
offset      {'type':'integer','minimum':0}                                  default=0

path product_id: {'type':'integer','minimum':1}  required=True
```

Every constraint written in Python reached the OpenAPI document. The docs and the validation cannot
drift apart, because they are the same declaration.

### List parameters

`tags: Annotated[list[str] | None, Query()]` is populated by repeating the parameter:

```
?tags=wireless                     -> 4 products
?tags=wireless&tags=waterproof     -> 2 products
?tags=wired&tags=premium           -> 2 products
```

Without the explicit `Query()`, FastAPI would read a `list` annotation as a request body rather than
a query parameter. That is the one case where the marker is load-bearing rather than decorative.

### Pagination

The response is an envelope, not a bare list:

```json
{"total": 12, "count": 4, "limit": 4, "offset": 4, "items": [...]}
```

`total` is the count after filtering but before slicing. Returning only the page would leave the
client unable to tell whether more results exist or how many pages there are. An offset past the end
returns `count: 0` with `total: 12` and a 200, not a 404 - an empty page of a real result set is a
successful request.

### Path parameter constraints

```python
product_id: Annotated[int, Path(ge=1)]
```

`Path()` takes the same constraints as `Query()`. With `ge=1`, `/products/0` and `/products/-3` are
422 before the function runs, so the only case left inside the body is a well-formed id that does
not exist, which is the 404. Separating "malformed" from "not found" is worth the one extra
argument.

## Why It Is Done This Way

**Why every filter is optional.** A bare `GET /products` returns the first page of everything.
Required filters would force a client to know the schema before it could make a first call.

**Why the cross-field rule is the one thing written by hand.**

```python
if min_price is not None and max_price is not None and min_price > max_price:
```

FastAPI validates each parameter in isolation, so it cannot know that `min_price=300` combined with
`max_price=100` is nonsense. Both values are individually valid. Rules spanning two fields need a
model, which is `model_validator` in module 05. This hand-written check is the marker for what that
module solves.

**Why 422 and not 400 for that check.** The request was syntactically fine and semantically
impossible, which is exactly what 422 means. It also keeps the status code consistent with the
automatic validation errors, so a client has one code to handle rather than two. The response *body*
is not yet consistent - the automatic errors return a structured list, mine returns a plain string.
That inconsistency is the problem module 06 fixes.

**Why `total` and `count` are both returned.** `total` is how many matched, `count` is how many are
in this page. Clients need both, and computing one from the other is not possible at the boundary.

**Why `tags` requires all tags to match rather than any.** `issubset` gives AND semantics, which is
what a filter usually means - narrowing, not widening. OR would need a separate parameter, and
guessing at it now would be scope creep.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8.

```
--- no filters, defaults applied ---
200  /products                                  total=12 count=12

--- single filters ---
200  /products?category=audio                   total=4   [Bluetooth Earbuds, Desk Speaker Pair, Studio Headphones, Studio Microphone]
200  /products?q=studio                         total=2   [Studio Headphones, Studio Microphone]
200  /products?min_price=200                    total=3   [NAS Drive 4TB, Smart Watch, Studio Headphones]
200  /products?max_price=50                     total=2   [SD Card 256GB, Wireless Mouse]
200  /products?min_rating=4.5                   total=4
200  /products?in_stock=false                   total=3   [Desk Speaker Pair, Ergonomic Trackball, NAS Drive 4TB]

--- list parameter ---
200  /products?tags=wireless                    total=4
200  /products?tags=wireless&tags=waterproof    total=2   [Fitness Tracker, Smart Watch]
200  /products?tags=wired&tags=premium          total=2   [Mechanical Keyboard, Studio Microphone]

--- sorting ---
200  /products?sort_by=price&order=desc&limit=3   [Smart Watch, Studio Headphones, NAS Drive 4TB]
200  /products?sort_by=rating&order=desc&limit=3  [Smart Watch, Mechanical Keyboard, Studio Headphones]

--- pagination ---
200  /products?limit=4&offset=0                 total=12 count=4
200  /products?limit=4&offset=4                 total=12 count=4
200  /products?limit=4&offset=8                 total=12 count=4
200  /products?limit=4&offset=99                total=12 count=0

--- combined ---
200  /products?category=audio&min_price=100&in_stock=true&sort_by=price&order=asc
                                                total=2   [Studio Microphone, Studio Headphones]

--- automatic 422s, zero lines of code in the function body ---
422  ?limit=0  ?limit=500  ?offset=-1  ?min_rating=9  ?min_price=-5
422  ?q=a      ?category=furniture     ?sort_by=colour  ?limit=abc

--- cross-field check, the one rule written by hand ---
422  /products?min_price=300&max_price=100
     "min_price (300.0) cannot exceed max_price (100.0)"

--- path parameter ---
200  /products/1              {"id":1,"name":"Studio Headphones",...}
404  /products/999            {"detail":"No product with id 999"}
422  /products/0              Input should be greater than or equal to 1
422  /products/-3             Input should be greater than or equal to 1
422  /products/abc            Input should be a valid integer
200  /products/categories     ["audio","wearables","peripherals","storage"]
```

## What I Learned

- The eleven-parameter signature reads badly, and that is a real signal rather than a style
  complaint. Module 09 groups the pagination pair into a reusable dependency, and looking at this
  function is what makes the reason obvious.
- `Query()` is not optional for a `list` parameter. Annotating `tags: list[str]` without it makes
  FastAPI treat it as a request body, and the failure is confusing because the parameter simply
  never populates.
- Constraints declared in the signature end up in the OpenAPI schema, which means the documentation
  literally cannot go stale relative to the validation. This is a stronger guarantee than it first
  appears.
- `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in this Starlette version in favour of
  `HTTP_422_UNPROCESSABLE_CONTENT`. Same number, renamed constant. It emits a warning that is
  invisible unless warnings are turned into errors.
- The error *body* format is not yet consistent: FastAPI's automatic 422s return a structured list
  under `detail`, while the hand-raised one returns a plain string. A client would have to handle
  both. That is a genuine flaw in this module, and it is what module 06 exists to fix.

## Navigation

[Previous](../02-routing/) | [All modules](../README.md) | [Next](../04-request-body-and-response-models/)
