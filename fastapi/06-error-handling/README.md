# 06 - Error Handling

## What This Project Does

Gives the API a single error contract. Every failure - a 404 we raised, an automatic 422 from
Pydantic, a 405 from the router before any code ran, a 418 from a plain `HTTPException`, or an
unhandled `ZeroDivisionError` - comes back in exactly the same JSON shape.

This closes the gap flagged in modules 03, 04 and 05: FastAPI's automatic validation errors returned
a bare `{"detail": [...]}` list while hand-raised errors returned `{"detail": "a string"}`, and a
client had to handle both.

## Topics Covered

- `HTTPException` and choosing the right status code
- Custom exception classes and `app.add_exception_handler`
- Overriding the default `RequestValidationError` response
- Normalising Starlette's own 404 and 405
- A consistent error envelope across the whole API
- Not leaking internal details in a 500 response
- Logging unhandled exceptions with a reference the client can quote

## Project Layout

```
06-error-handling/
|-- main.py                  app, handler registration, /teapot, /health
|-- errors.py                AppError base + 4 subclasses, ErrorCode enum. No FastAPI imports.
|-- handlers.py              4 exception handlers, one response builder
|-- schemas.py               ErrorResponse envelope + product schemas
|-- config.py                settings from the shared root .env
|-- logging_config.py        logging setup
|-- data.py                  in-memory catalogue
|-- routers/
    |-- __init__.py
    |-- products.py          7 routes, 3 of which fail on purpose
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

To see production behaviour, which hides more:

```bash
ENVIRONMENT=production DEBUG=false uvicorn main:app
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/products` | Search. `min_price > max_price` triggers a cross-field 422 |
| GET | `/products/{id}` | Get one, or a 404 |
| POST | `/products` | Create, or a 409 on a duplicate SKU |
| DELETE | `/products/{id}` | Delete, or a 404 |
| GET | `/products/boom` | Deliberate `ZeroDivisionError`, produces a 500 |
| GET | `/products/upstream` | Simulated dependency failure, produces a 503 |
| GET | `/products/flaky` | Fails about half the time, for watching logs |
| GET | `/teapot` | Plain `HTTPException(418)` |
| GET | `/health` | Health check |

## The Envelope

```json
{
  "error": {
    "code": "not_found",
    "message": "No product with id 999",
    "details": [],
    "reference": "5f058ddb8dfd"
  }
}
```

- `code` is a stable enum value. Clients branch on this.
- `message` is for humans. It can be reworded or translated; branching on it is a bug waiting to
  happen.
- `details` carries per-field failures, empty when the error is not field-specific.
- `reference` correlates the response with the server log line.

## How It Works

### Four handlers, one builder

```python
app.add_exception_handler(AppError, handle_app_error)
app.add_exception_handler(RequestValidationError, handle_validation_error)
app.add_exception_handler(StarletteHTTPException, handle_http_exception)
app.add_exception_handler(Exception, handle_unexpected_error)
```

Each one gathers different information, and all four finish by calling the same `build_response`.
That single funnel is what makes the shape consistent - not a convention each handler is trusted to
follow.

Registration order does not matter. Starlette dispatches on exception type and picks the most
specific registered handler for the class raised, so `NotFoundError` reaches `handle_app_error`
rather than the catch-all despite both matching.

### Every failure mode, checked

```
404  our NotFoundError                code=not_found              ref=5f058ddb8dfd
422  FastAPI automatic validation     code=validation_error       ref=405109755645  details=['query.limit']
422  our cross-field rule             code=validation_error       ref=dfb4953334cf  details=['query.min_price','query.max_price']
409  our ConflictError                code=conflict               ref=5e764aab399b  details=['body.sku']
503  our UpstreamError                code=upstream_unavailable   ref=afde489e29f7
418  plain HTTPException              code=invalid_request        ref=8df0fdebc6cd
405  starlette 405                    code=method_not_allowed     ref=87225f4aba3c
404  starlette 404 unmatched route    code=not_found              ref=218fd84d79fb
500  unhandled ZeroDivisionError      code=internal_error         ref=729bef3f99d3

distinct top-level key sets : {('error',)}
distinct error key sets     : {('code','details','message','reference')}
all identical               : True
```

Nine different failure paths, one structure. The two that matter most are the ones nothing in this
codebase wrote:

- `GET /no-such-route` - the router raises before any endpoint is selected, so without the
  `StarletteHTTPException` handler the envelope would hold everywhere except the path a confused
  client is most likely to hit.
- `PUT /health` - a 405 from the same place, for the same reason.

### The automatic 422, reshaped

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request failed validation",
    "details": [
      {
        "field": "query.limit",
        "message": "Input should be greater than or equal to 1",
        "type": "greater_than_equal"
      }
    ],
    "reference": "405109755645"
  }
}
```

Pydantic's `loc` is a tuple such as `("query", "limit")` or `("body", "items", 0, "sku")`. Joining it
with dots gives a path a client can map straight back to an input field, including the array index.
Nothing is lost in the reshape.

The hand-written cross-field rule now produces the same shape, with two entries in `details` because
two parameters are jointly at fault. In module 03 this was a plain string and structurally
incompatible with the automatic errors.

### The 500, and what it does not say

The deliberate bug:

```python
denominator = 0
return {"result": 42 / denominator}
```

In production:

```json
{
  "error": {
    "code": "internal_error",
    "message": "An unexpected error occurred. Quote the reference when reporting it.",
    "details": [],
    "reference": "742ed03cbd4f"
  }
}
```

Probed against the raw response text:

```
contains 'Traceback'          : False
contains 'ZeroDivisionError'  : False
contains 'division by zero'   : False
contains 'products.py'        : False
contains 'site-packages'      : False
contains 'denominator'        : False
contains 'D:\'                : False
contains 'line '              : False
```

Meanwhile the full traceback, including the file and line, is in the server log under the same
reference. The information is not destroyed, it is redirected to the only party entitled to it.

In development, `details` additionally carries the exception **type** - `ZeroDivisionError` - and
nothing else:

```json
{"field": null,
 "message": "Unhandled ZeroDivisionError. The traceback is in the server log.",
 "type": "ZeroDivisionError"}
```

**Corrected after module 08.** This originally included `str(exc)` as well, described here as a
"deliberate development trade". A contract test written in module 08 then demonstrated that same
line returning a full `postgres://user:pw@host/db` connection string to the client, because that is
what the exception message happened to contain. Exception messages routinely carry credentials, SQL
fragments and file paths, and there is no way to know in advance which ones do - which is exactly
the argument this README already made two paragraphs further down, applied inconsistently.

The type name alone is safe, because it is a fixed identifier with nothing interpolated into it. The
whole block is still gated on `settings.debug and not settings.is_production`, so a half-configured
deployment fails closed.

### Reference correlation

Server log:

```
09:41:32 WARNING  api.errors: GET /products/999 -> 404 not_found [ref=90374af64b15] No product with id 999
09:41:32 INFO     api.errors: GET /products -> 422 validation_error [ref=d6fa2c83dab7] 1 problem(s)
09:41:32 ERROR    api.errors: GET /products/upstream -> 503 upstream_unavailable [ref=2292b339b071] The pricing service did not respond within 2000ms
09:41:32 WARNING  api.errors: GET /teapot -> 418 invalid_request [ref=b73ca8dece10]
09:41:32 WARNING  api.errors: GET /no-such-route -> 404 not_found [ref=9ceb3113b57a]
```

Client response:

```
body reference    : 729bef3f99d3
X-Error-Reference : 729bef3f99d3
match             : True

5 requests -> ['80f6625fb047','cb627fb310a2','40524cbcef79','ad9543ced06a','5c0785269b15']
all unique  : True
```

A user reporting "it broke" is nearly useless. A user reporting "it broke, reference 729bef3f99d3"
locates the exact traceback in one grep. The reference is also returned as a header so a client can
log it without parsing the body.

Log levels are chosen rather than uniform: a 422 is `INFO` because bad client input is normal
traffic, a 404 or 409 is `WARNING`, and anything 5xx is `ERROR`. Logging every validation failure at
`ERROR` is how alerting gets ignored.

### Documented in OpenAPI

```
GET    /products/{product_id}   {'200':'ProductRead','404':'ErrorResponse','409':'ErrorResponse',
                                 '422':'ErrorResponse','500':'ErrorResponse','503':'ErrorResponse'}
POST   /products                {'201':'ProductRead','404':'ErrorResponse', ... }
DELETE /products/{product_id}   {'204':'-','404':'ErrorResponse', ... }
```

`ERROR_RESPONSES` is attached at the router and app level rather than per route, so a route added
later inherits the documentation instead of quietly omitting it.

## Why It Is Done This Way

**Why `errors.py` imports nothing from FastAPI.** These are plain exceptions. A service layer or a
repository can raise `NotFoundError` without importing a web framework, and the same exception could
be reused by a CLI or a background worker. Only `handlers.py` knows about HTTP.

**Why the status code lives on the exception class.** `NotFoundError.status_code = 404` means a
not-found is a 404 everywhere. Passing the code at the raise site invites the same condition
becoming a 400 in one place and a 404 in another.

**Why `ValidationRuleError` shares 422 and `validation_error` with FastAPI's own failures.** From a
client's point of view "your input was unacceptable" is one situation. Giving our version a distinct
code would force two code paths for one outcome.

**Why `UpstreamError` is 503 and not 500.** The fault is not in this service and the condition is
expected to be temporary. 503 tells a client that retrying is reasonable; 500 tells it to give up.
That distinction is the difference between a self-healing system and a support ticket.

**Why the 500 message is fixed rather than descriptive.** Any detail derived from the exception is a
detail derived from internal state. Exception messages routinely contain SQL fragments, file paths,
and occasionally credentials from a connection string. A fixed message plus a reference gives the
user something actionable without guessing what might be safe.

**Why `logger.exception` and not `logger.error`.** `exception()` attaches the traceback to the log
record. `error()` would log the message and discard exactly the part needed for debugging.

**Why `force=True` in `basicConfig`.** Uvicorn installs its own handlers before the application
module is imported. Without `force=True`, `basicConfig` finds the root logger already configured and
silently does nothing, so the `LOG_LEVEL` setting has no effect and the reason is invisible.

**Why `/products/boom` exists.** A test that only exercises anticipated failures does not prove the
catch-all works. The only honest demonstration is a genuine unhandled exception with no `try` block
anywhere near it.

## Known Gaps

- The `reference` is generated inside the error handlers, so successful requests do not have one.
  Module 07 moves it into middleware, where every request gets an id and it can be logged for
  successful requests too.
- Logging is plain text. Structured JSON logs, which is what a log aggregator actually needs, belong
  with the deployment work in module 16.
- Nothing here rate-limits or deduplicates repeated identical errors. A tight client retry loop
  would flood the log.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8. `TestClient(app, raise_server_exceptions=False)` is
required for the 500 case - the default re-raises the exception into the test instead of returning
the response a real client would receive.

```
=== nine failure modes, one envelope ===
404  our NotFoundError              code=not_found            details=[]
422  FastAPI automatic validation   code=validation_error     details=['query.limit']
422  our cross-field rule           code=validation_error     details=['query.min_price','query.max_price']
409  our ConflictError              code=conflict             details=['body.sku']
503  our UpstreamError              code=upstream_unavailable
418  plain HTTPException            code=invalid_request
405  starlette 405                  code=method_not_allowed
404  starlette unmatched route      code=not_found
500  unhandled ZeroDivisionError    code=internal_error

distinct top-level key sets : {('error',)}
distinct error key sets     : {('code','details','message','reference')}
all identical               : True

=== production 500 leaks nothing ===
Traceback False | ZeroDivisionError False | division by zero False | products.py False
site-packages False | denominator False | D:\ False | line  False
details is empty : True   reference still present : 742ed03cbd4f

=== reference correlation ===
body reference == X-Error-Reference : True
5 requests, all references unique   : True

=== success paths unaffected ===
200  /health          {"status":"ok","version":"0.1.0","environment":"development"}
200  /products        5 products
200  /products/1      {"id":1,"sku":"HP-2200",...}
201  POST /products   {"id":6,"sku":"NW-7700",...}
204  DELETE /products/2  (no body)

=== openapi documents the error shape on every route ===
GET/POST/DELETE /products*  ->  404/409/422/500/503 all ErrorResponse
```

## What I Learned

- Two of the nine failure modes never reach application code. An unmatched route and a wrong method
  are raised by the router, so handling only `AppError` and `RequestValidationError` would leave the
  envelope broken on exactly the requests a confused client makes most.
- Registering a handler for bare `Exception` is what turns a 500 from an information leak into a
  reference number. Without it Starlette returns its own plain-text 500, and with `debug=True` it
  returns a full HTML traceback page.
- `TestClient` re-raises server exceptions by default, so the 500 path is invisible unless
  `raise_server_exceptions=False` is passed. It is possible to write a passing test suite that never
  once exercises the catch-all handler.
- `logging.basicConfig` silently does nothing when uvicorn has already configured the root logger.
  `force=True` is the fix, and the failure gives no warning at all - the level setting just has no
  effect.
- Choosing log levels per error class matters more than it looks. Validation failures are ordinary
  traffic; logging them at `ERROR` is how a team learns to ignore its own alerts.
- Putting the status code on the exception class rather than at the raise site removes a whole
  category of inconsistency, and it also makes the handler trivial - it never has to decide anything.
- Including `str(exc)` in a debug-mode response felt harmless and was not. A test in module 08 showed
  it returning a database password. Writing "exception messages routinely contain credentials" in
  one paragraph and then including the exception message in the code two paragraphs earlier is
  exactly the kind of inconsistency a test catches and a careful read does not.

## Navigation

[Previous](../05-pydantic-and-settings/) | [All modules](../README.md) | [Next](../07-middleware-and-cors/)
