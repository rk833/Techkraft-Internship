# 05 - Pydantic Models and Settings

## What This Project Does

An order API taking a three-level nested payload: an order containing a customer, containing an
address, alongside a list of line items. It also reads its configuration from the shared `.env` at
the repository root.

The theme is that almost every rule an order has to satisfy belongs in the schema rather than in the
endpoint. `create_order` contains one `if` statement, and that one is about an operational limit
rather than about the shape of an order.

It also closes both gaps left open in module 04: unknown fields are now rejected, and the cross-field
rule module 03 had to hand-write in the endpoint is now part of the model.

## Topics Covered

- `BaseModel`, `Field()` constraints, and reusable `Annotated` types
- Nested models and lists of models
- `field_validator` in `mode="after"` and `mode="before"`
- `model_validator(mode="after")` for cross-field rules
- `computed_field` for derived, output-only values
- `model_config`: `extra="forbid"`, `populate_by_name`, `from_attributes`
- Field aliases
- The mutable default question, and what Pydantic actually does about it
- `Decimal` for money, and how it serialises
- `pydantic-settings`, `.env` loading, and `lru_cache`
- Pydantic v1 vs v2 differences worth knowing

## Project Layout

```
05-pydantic-and-settings/
|-- main.py                  app, /config, /health
|-- config.py                Settings, resolves the repo-root .env from __file__
|-- schemas.py               the substance of this module
|-- data.py                  in-memory store + LegacyOrderRow dataclass
|-- routers/
    |-- __init__.py
    |-- orders.py            4 routes, deliberately thin
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

Note the page title reads "Order API (FastAPI Learning Journey)" - the second half comes from
`APP_NAME` in the root `.env`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/orders` | Place an order |
| GET | `/orders` | List orders |
| GET | `/orders/legacy-demo` | `from_attributes` demonstration |
| GET | `/orders/{order_id}` | Get one order |
| GET | `/config` | Show effective settings |
| GET | `/health` | Service health check |

## How It Works

### Settings from the shared .env

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
```

Resolved from `__file__`, not from the working directory. This is the whole reason a single `.env`
can serve every module - `uvicorn` is launched from inside the module folder, so a relative
`env_file=".env"` would look in the wrong place and silently fall back to defaults.

```
app_name               FastAPI Learning Journey
environment            development
debug                  True
log_level              INFO
max_items_per_order    20
is_production          False
env_file               D:\AI internship\fastapi\.env
```

`extra="ignore"` is required, not optional. The shared `.env` also holds database URLs, a JWT
secret and LLM keys; without it, `Settings()` would refuse to load the file for containing keys it
does not declare.

`@lru_cache` on `get_settings()` means the file is parsed once per process rather than per request,
and gives module 09 a clean seam for injecting test settings.

### Validators do the normalising

One valid order, showing what the schema did to the input on the way through:

```
skus in   : ["kb-4400", "MS-1200"]   ->  out: ['KB-4400', 'MS-1200']
country in: "gb"                     ->  out: "GB"
notes in  : "   " (whitespace)       ->  out: None
tags in   : "priority" (bare string) ->  out: ['priority']
line_total computed                  ->  ['145.00', '85.00']
subtotal 230.00  discount 10.00  total 220.00
```

Four different mechanisms in one request:

- `mode="after"` validators uppercased the SKU and country, and collapsed the whitespace-only note
  to `None`. After-mode runs once the value is already the right type, so it never has to defend
  against being handed an int.
- A `mode="before"` validator accepted the bare string `"priority"` where a list was expected. This
  only works in before-mode: by after-mode, a string would already have been rejected as not a list.
- `computed_field` produced `line_total` and `subtotal`.

### model_validator for the cross-field rule

Module 03 had to write this inside the endpoint, because FastAPI validates parameters one at a time:

```
422  discount > subtotal    Value error, discount 9999.00 exceeds subtotal 230.00
```

Now it lives on the model. It applies anywhere the model is used, and it arrives in the same
structured 422 as every other validation error instead of being a special case.

A rule about elements *within* one field stays a `field_validator`, because the validator already
receives the whole list:

```
422  duplicate sku after upper    items: Value error, duplicate SKUs: ZZ-9999
```

Worth noting that the two SKUs sent were `ZZ-9999` and `zz-9999`. The uppercase normalisation ran on
each item first, so the duplicate check saw them as identical. Validator ordering did real work
there.

### extra="forbid" closes the module 04 gap

```
422  unknown top level key   is_admin: Extra inputs are not permitted
422  unknown nested key      customer.vip: Extra inputs are not permitted
```

In module 04 the first of those returned 201 and silently dropped the field. Now a client typo is an
error rather than a setting that quietly does nothing. It applies through the nesting because every
request schema inherits from `StrictModel`.

It also makes `computed_field` genuinely read-only. A client trying to forge a line total:

```
422  client sends line_total   items.0.line_total: Extra inputs are not permitted
```

### Nested errors carry the full path

```
422  customer.address.country   String should match pattern '^[A-Za-z]{2}$'
422  customer.email             value is not a valid email address: An email address must have an @-sign.
422  items.1.quantity           Input should be greater than or equal to 1
422  items.0.unitPrice          Decimal input should have no more than 2 decimal places
```

`items.1.quantity` names the array index. A client can point at the exact input that failed, three
levels down, with no error-mapping code on our side.

### Aliases

`unit_price` carries `alias="unitPrice"`, and `populate_by_name=True` keeps the Python name working:

```
201  unit_price (python name)   unit_price=12.50 line_total=25.00 total=25.00
201  unitPrice   (alias)        unit_price=12.50 line_total=25.00 total=25.00
422  both spellings at once     Extra inputs are not permitted
```

The response always uses the Python name:

```
['line_total', 'name', 'quantity', 'sku', 'unit_price']
```

Sending both spellings is correctly rejected, because `extra="forbid"` treats the second one as an
unknown key once the first has been consumed.

### from_attributes

`GET /orders/legacy-demo` returns a `LegacyOrderRow` - a dataclass, not a dict:

```
200  {"id":9001,"status":"paid",...}
     id 9001  items 2  subtotal 230.00  total 220.00
     line_total read from a @property: ['145.00', '85.00']
```

`from_attributes=True` lets Pydantic read attributes rather than dict keys, including values that
come from a `@property` rather than being stored. This is exactly the mechanism module 11 uses to
turn SQLAlchemy rows into responses; doing it against a dataclass first means that module is about
the database rather than about this conversion.

### Money as Decimal

```python
Money = Annotated[Decimal, Field(max_digits=10, decimal_places=2, ge=0)]
```

Declared once and reused for every price, so a change to the rules lands everywhere. It catches
precision errors at the boundary:

```
422  items.0.unitPrice   Decimal input should have no more than 2 decimal places
```

In JSON, `Decimal` serialises as a **string**, not a number:

```
"subtotal": "230.00", "discount": "10.00", "total": "220.00"
```

That is deliberate on Pydantic's part and it is correct. JSON numbers are IEEE 754 doubles, and
JavaScript would parse `220.00` into a float that cannot represent every 2-decimal value exactly.
Keeping money as a string preserves it precisely. Any client consuming this needs to know, so it is
worth documenting on a real API.

## The mutable default question

Nearly every Python guide warns about `tags: list[str] = []` as a shared-mutable-default bug. In
Pydantic that warning is wrong, and it is worth knowing which is which:

```
pydantic 'tags: list[str] = []'   second instance sees it:  False   (b.tags=[])
plain python 'def f(tags=[])'     second call sees it:      True
```

Pydantic deep-copies a default for each instance, so the bug does not occur. The plain Python
function has it exactly as advertised.

`default_factory` is still used here, for reasons that are not about safety:

- Plain dataclasses and normal functions *do* have the bug, so it is the right habit to carry.
- It is required for any default that must be computed per instance, such as a timestamp or a UUID.
- It states the intent plainly.

## Pydantic v1 vs v2

Older tutorials will not match this code. The differences that actually bite:

| v1 | v2 |
|----|----|
| `@validator("x")` | `@field_validator("x")`, needs `@classmethod` |
| `@root_validator` | `@model_validator(mode="before" \| "after")` |
| `class Config:` | `model_config = ConfigDict(...)` |
| `orm_mode = True` | `from_attributes=True` |
| `allow_population_by_field_name` | `populate_by_name` |
| `.dict()` / `.json()` | `.model_dump()` / `.model_dump_json()` |
| `parse_obj()` | `model_validate()` |
| `Field(..., regex=)` | `Field(..., pattern=)` |
| `min_items` / `max_items` | `min_length` / `max_length` |
| `BaseSettings` in pydantic | `BaseSettings` in `pydantic-settings` |

The last one is the most common stumbling block, because the import simply fails rather than
behaving differently.

## Why It Is Done This Way

**Why `StrictModel` is a base class rather than config repeated per model.** Five request schemas
need identical config. Repeating `model_config` five times means the sixth model added later gets
forgotten, and `extra="forbid"` failing open is exactly the kind of gap nothing warns about.

**Why request and response schemas are separate hierarchies.** `OrderItemCreate` forbids extras and
supports aliases; `OrderItemRead` allows `from_attributes`. Those are opposite needs. Sharing one
class would mean whichever direction is stricter loses.

**Why `max_items_per_order` is in settings and `min_length=1` on the items list is in the schema.**
An order with zero items is not an order, so that is a property of the type. Twenty items being the
ceiling is an operational choice that could differ per environment, so it belongs in config. The
split is between "what an order is" and "what this deployment allows".

**Why `docs_url` is disabled in production.** Interactive docs on a public API are a free map of
every endpoint. Driving it from `settings.is_production` rather than from a hardcoded flag means the
same image behaves correctly in both places, which is what module 16 needs.

**Why `/config` exists and returns only safe values.** Being able to ask a running service what
configuration it actually loaded saves a lot of guessing. It also has to be curated by hand rather
than dumping `Settings()` wholesale, because the shared `.env` holds a JWT secret and API keys.

**Why the endpoint is nearly empty.** Every rule in the schema is enforced consistently, documented
automatically in OpenAPI, and reusable. A rule written as an `if` in a handler is none of those.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8, Pydantic 2.13.4.

```
=== settings from the shared root .env ===
app_name FastAPI Learning Journey | environment development | debug True
log_level INFO | max_items_per_order 20 | is_production False
env_file D:\AI internship\fastapi\.env

=== valid order, normalisation applied ===
201  skus  ["kb-4400","MS-1200"] -> ['KB-4400','MS-1200']
     country "gb" -> "GB"   notes "   " -> None   tags "priority" -> ['priority']
     line_total ['145.00','85.00']  subtotal 230.00  discount 10.00  total 220.00
     money serialised as str, not float

=== aliases ===
201  unit_price (python name)   unit_price=12.50 line_total=25.00
201  unitPrice   (alias)        unit_price=12.50 line_total=25.00
422  both spellings at once     Extra inputs are not permitted
     response keys: ['line_total','name','quantity','sku','unit_price']

=== model_validator ===
422  discount > subtotal   Value error, discount 9999.00 exceeds subtotal 230.00

=== field_validator over the list ===
422  ZZ-9999 + zz-9999     items: Value error, duplicate SKUs: ZZ-9999

=== extra=forbid ===
422  is_admin              Extra inputs are not permitted
422  customer.vip          Extra inputs are not permitted
422  items.0.line_total    Extra inputs are not permitted  (computed field is output only)

=== nested paths ===
422  customer.address.country  String should match pattern '^[A-Za-z]{2}$'
422  customer.email            value is not a valid email address
422  items.1.quantity          Input should be greater than or equal to 1

=== field constraints ===
422  items                     List should have at least 1 item after validation, not 0
422  currency                  Input should be 'GBP', 'EUR', 'USD' or 'NPR'
422  discount                  Input should be greater than or equal to 0
422  items.0.unitPrice         Decimal input should have no more than 2 decimal places
422  items.0.sku               String should match pattern '^[A-Za-z0-9-]+$'

=== from_attributes ===
200  /orders/legacy-demo   LegacyOrderRow dataclass -> OrderRead
     id 9001  items 2  subtotal 230.00  total 220.00
     line_total read from a @property: ['145.00','85.00']

=== read back ===
200  /orders/1      404  /orders/9999

=== mutable defaults ===
pydantic 'tags: list[str] = []'   shared across instances: False
plain python 'def f(tags=[])'     shared across calls:     True
```

## What I Learned

- The mutable default warning does not apply to Pydantic. It deep-copies defaults per instance, so
  `= []` is safe there while the identical pattern in a plain function is not. Most guides state
  this incorrectly. `default_factory` is still the better habit, but for different reasons than the
  ones usually given.
- Validator ordering is load-bearing. The duplicate-SKU check only caught `ZZ-9999` and `zz-9999`
  because the uppercase validator had already run on each item. Reverse that and the rule silently
  stops working, with no error to point at it.
- `mode="before"` and `mode="after"` are not interchangeable. Accepting a bare string where a list
  is expected is only possible in before-mode; normalising a string is only safe in after-mode.
- `Decimal` serialises to a JSON string, not a number. Surprising at first, and correct - JSON
  numbers are doubles and cannot hold every 2-decimal value exactly. Any client needs telling.
- `extra="forbid"` does more than catch typos. It is what makes a `computed_field` genuinely
  read-only, because the forged input has nowhere to land.
- `pydantic-settings` refuses to load an `.env` containing keys the class does not declare, unless
  `extra="ignore"` is set. With a shared `.env` covering eighteen modules, that is mandatory rather
  than a nicety.
- Resolving the `.env` path from `__file__` instead of the working directory is what makes one
  shared config file work at all. A relative path fails silently by falling back to defaults, which
  is the worst possible failure mode.

## Navigation

[Previous](../04-request-body-and-response-models/) | [All modules](../README.md) | [Next](../06-error-handling/)
