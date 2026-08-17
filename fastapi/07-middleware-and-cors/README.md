# 07 - Middleware and CORS

## What This Project Does

Wraps the API in a middleware stack that gives every request an id, times it, logs it, compresses
large responses, and lets a browser on a different origin actually call it.

It also promotes the `reference` from module 06. There it was generated inside the error handlers,
so only failing requests had one. It is now a request id assigned in middleware, present on every
response, echoed in a header, and injected into every log line for that request.

Building this surfaced a real bug that is invisible in the code: **a 500 response bypasses every
piece of user middleware**, including CORS. That is documented below with the measurement and the
fix, because it is the most useful thing in this module.

## Topics Covered

- What middleware is and where it sits in the request lifecycle
- Middleware ordering, and why the last registered is the outermost
- `CORSMiddleware`, preflight, and `expose_headers`
- Pure ASGI middleware vs `@app.middleware("http")`, and when the difference matters
- `ContextVar` for per-request state
- A logging `Filter` that injects the request id into every record
- `GZipMiddleware`
- `lifespan` for startup and shutdown
- Where Starlette's own error handling sits relative to yours

## Project Layout

```
07-middleware-and-cors/
|-- main.py                  app, lifespan, middleware registration (order matters)
|-- middleware.py            RequestContextMiddleware (pure ASGI) + security headers (decorator)
|-- context.py               the request id ContextVar
|-- logging_config.py        RequestIdFilter, injects the id into every log record
|-- config.py                settings, including CORS origin parsing
|-- errors.py                carried over from module 06, unchanged
|-- handlers.py              carried over, reference now read from the ContextVar
|-- schemas.py               error envelope + product schemas
|-- data.py                  in-memory catalogue
|-- routers/products.py      products, plus /slow and /bulk for exercising middleware
|-- static/cors-demo.html    a real browser page for testing CORS cross-origin
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

To test CORS properly you need a second origin. In another terminal:

```bash
python -m http.server 5500 --directory static
```

Then open `http://127.0.0.1:5500/cors-demo.html`. That origin is listed in `CORS_ALLOWED_ORIGINS` in
the shared `.env`. Opening the same page as `http://localhost:5500` instead gets blocked - a
different hostname is a different origin, even on the same machine.

## The Middleware Stack

Registration order in `main.py` is inside-out. The **last** middleware added is the **outermost**.

```python
app.add_middleware(GZipMiddleware, ...)                    # 1, innermost
app.add_middleware(RequestContextMiddleware, ...)          # 2
add_security_headers_middleware(app)                       # 3
app.add_middleware(CORSMiddleware, ...)                    # 4, outermost
```

Which produces, measured by walking `app.middleware_stack`:

```
0. ServerErrorMiddleware      <- Starlette's own, always outermost, not ours
1. CORSMiddleware
2. BaseHTTPMiddleware         <- the security headers decorator
3. RequestContextMiddleware
4. GZipMiddleware
5. ExceptionMiddleware        <- where registered exception handlers run
6. AsyncExitStackMiddleware
7. APIRouter
```

A request travels down that list and a response travels back up it.

## The Bug Worth Knowing About

`ServerErrorMiddleware` is at position 0, **outside** everything registered by the application. It is
what invokes the handler registered for bare `Exception`. So a 500 response is generated above the
entire user stack and never travels back through it.

Measured on the first build, before any fix:

```
status 500
x-request-id           : None
x-response-time-ms     : None
x-content-type-options : None
body reference         : -            <- ContextVar already reset
access-control-allow-origin : None
```

Every one of those is a real consequence:

- No request id in the header or the body, so the 500 is uncorrelatable with its log line - the exact
  case where correlation matters most.
- No CORS header, which means a browser does not show the client a 500. It shows an opaque network
  failure and the actual error is unreadable from JavaScript. This is the single most confusing
  class of bug in a browser-facing API, and nothing in the source hints at it.

### The fix

`RequestContextMiddleware` catches the exception itself and produces the error response from inside
the stack, so it travels out through every layer like any other response:

```python
try:
    await self.app(scope, receive, send_with_headers)
except Exception as exc:
    if response_started or self.on_unhandled is None:
        raise                       # headers already sent, nothing valid left to do
    response = await self.on_unhandled(Request(scope, receive), exc)
    await response(scope, receive, send_with_headers)
```

`on_unhandled` is the same `handle_unexpected_error` from module 06, so the envelope and the
redaction rules are unchanged - only where it runs has moved. The security-headers middleware was
also moved outside `RequestContextMiddleware` so it decorates these responses too.

Measured after:

```
status 500
x-request-id           : c836cb79d365
x-response-time-ms     : 2.78
x-content-type-options : nosniff
body reference         : c836cb79d365
header == body ref     : True
access-control-allow-origin : http://localhost:3000
```

## How It Works

### Every response carries both headers

```
200  GET  /health                x-request-id=8cbafe89493a  x-response-time-ms=6.60
200  GET  /products              x-request-id=a54aaf7273d5  x-response-time-ms=0.80
404  GET  /products/999          x-request-id=a6c24521a486  x-response-time-ms=0.39
422  GET  /products?limit=0      x-request-id=72daf2349e24  x-response-time-ms=0.27
503  GET  /products/upstream     x-request-id=aafacba055a1  x-response-time-ms=0.34
200  GET  /docs                  x-request-id=a146ce1491d7  x-response-time-ms=0.15
404  GET  /no-such-route         x-request-id=8736cc916387  x-response-time-ms=0.15
405  PUT  /health                x-request-id=b084aaa2b691  x-response-time-ms=0.26
500  GET  /products/boom         x-request-id=c836cb79d365  x-response-time-ms=2.78
```

Including `/docs`, the router's own 404 and 405, and the 500.

The timing is real, not decorative:

```
slept    0ms  ->  x-response-time-ms=   0.36
slept  120ms  ->  x-response-time-ms= 121.13
slept  400ms  ->  x-response-time-ms= 401.30
```

### Pure ASGI, because of the ContextVar

`RequestContextMiddleware` is a plain ASGI callable rather than a `BaseHTTPMiddleware` subclass.
`BaseHTTPMiddleware` runs the downstream application in a separate anyio task, so a `ContextVar` set
before `call_next` is not reliably visible inside the endpoint. Pure ASGI middleware runs in the same
task, so the value propagates.

The cost is that changing a response header means wrapping `send` and editing the
`http.response.start` message, because by then the response is already streaming:

```python
if message["type"] == "http.response.start":
    out = MutableHeaders(scope=message)
    out[REQUEST_ID_HEADER] = request_id
```

The upside is that it works for streaming and file responses too, which the `Response` object route
does not.

The security headers use the decorator form, `@app.middleware("http")`, because all it does is
decorate a finished response - the limitations never bite:

```
x-content-type-options     nosniff
x-frame-options            DENY
referrer-policy            no-referrer
```

The `scope["type"] != "http"` guard at the top is not optional. Lifespan and websocket scopes have
no `method` key, and a middleware assuming otherwise breaks startup with a confusing error.

### The ContextVar, end to end

```
10:14:26 INFO [-]            api.lifespan: startup: FastAPI Learning Journey in development mode
10:13:05 INFO [42f67d206a43] api.products: search category=None limit=20
10:13:05 INFO [42f67d206a43] api.request:  GET /products -> 200 in 1.05ms
10:13:05 WARNING [72c63188f2a6] api.errors: /products/999 -> 404 not_found: No product with id 999
10:13:05 INFO [72c63188f2a6] api.request:  GET /products/999 -> 404 in 0.73ms
```

`api.products` is an endpoint that never received a request id as an argument. It called
`get_request_id()` and got the right value. A `logging.Filter` puts it on every record, so no log
call has to remember to include it. The `-` default is what makes startup lines render before any
request exists.

Both directions line up:

```
/health   header=73b84a1bcb1b  body.request_id=73b84a1bcb1b  match=True
404       header=69355b246340  body.reference =69355b246340  match=True
500       header=c836cb79d365  body.reference =c836cb79d365  match=True
```

### Inbound request ids, trusted carefully

An inbound `X-Request-ID` is honoured so a trace can span several services, but it is echoed back in
a response header, so it cannot be trusted blindly:

```
valid client id           sent 'trace-abc123def456'         echoed 'trace-abc123def456'  honoured=True
too short                 sent 'abc'                        echoed '05c62011a284'        honoured=False
header injection attempt  sent 'aaaaaaaa\r\nX-Admin: true'  echoed '14185f047231'        honoured=False
too long                  sent 'x' * 200                    echoed '92ed087be69c'        honoured=False
illegal chars             sent 'abc<script>def'             echoed 'f9f8e3c09105'        honoured=False
```

Anything not matching `^[A-Za-z0-9._-]{8,64}$` is discarded and replaced.

### CORS

Allowed origin:

```
access-control-allow-origin        http://localhost:3000
access-control-allow-credentials   true
access-control-expose-headers      x-request-id, x-response-time-ms
```

Disallowed origin:

```
status 200 (the request is still served)
access-control-allow-origin      None
```

Worth understanding: the server does **not** refuse the request. It serves it and omits the header,
and the *browser* refuses to hand the response to JavaScript. CORS is a browser policy, not a server
access control. `curl` ignores it entirely, so CORS is never a substitute for authentication.

Preflight:

```
OPTIONS /products
status 200
access-control-allow-origin        http://localhost:3000
access-control-allow-methods       GET, POST, PATCH, DELETE, OPTIONS
access-control-allow-headers       Accept, Accept-Language, Authorization, Content-Language, Content-Type, x-request-id
access-control-max-age             600
x-request-id on preflight          None
```

The preflight has no request id because `CORSMiddleware` is outermost and short-circuits `OPTIONS`
before anything downstream runs. That is the correct trade: CORS being outermost is what puts CORS
headers on error responses, and a preflight carries no application response to correlate.

`expose_headers` is the line people miss. Without it, browser JavaScript can only read a small fixed
set of response headers. Our two would be present on the wire and visible in devtools, and
`response.headers.get("x-request-id")` would return `null`.

### Verified in a real browser

Headers alone cannot prove CORS works, so the demo page was served from `127.0.0.1:5500` against the
API on `127.0.0.1:8000` and driven for real.

`GET /health` from the page:

```
status              200
x-request-id        browser-1785472241205
x-response-time-ms  0.66
{"status":"ok",...,"request_id":"browser-1785472241205"}
```

JavaScript read both custom headers, which proves `expose_headers`. The client-supplied id was
honoured end to end and came back in the body.

`GET /products/boom` from the page:

```
status              500
x-request-id        browser-1785472251430
x-response-time-ms  3.55
{"error":{"code":"internal_error","message":"An unexpected error occurred...
```

The browser could read the 500 body. Before the fix this was an opaque network failure.

Network log from the browser, with zero console errors:

```
OPTIONS http://127.0.0.1:8000/health         -> 200
GET     http://127.0.0.1:8000/health         -> 200
GET     http://127.0.0.1:8000/products/boom  -> 500
OPTIONS http://127.0.0.1:8000/products       -> 200
POST    http://127.0.0.1:8000/products       -> 201
```

The `OPTIONS` before `GET /health` is a detail worth noticing: a GET is normally a simple request
needing no preflight, but the page sends a custom `X-Request-ID` header, and any non-standard header
makes a request non-simple. Adding one custom header doubled the request count.

### GZip

```
identity  content-encoding=None     content-length=140701
gzip      content-encoding='gzip'   content-length=2628
small response below minimum_size -> content-encoding=None
```

140 KB to 2.6 KB, about 53x, on deliberately repetitive JSON. Real payloads compress less
dramatically, but JSON's repeated key names compress well in general. `minimum_size=500` skips small
responses, where the CPU cost and the added header outweigh a few saved bytes.

### Lifespan

```
10:14:26 INFO [-] api.lifespan: startup: FastAPI Learning Journey in development mode
10:14:26 INFO [-] api.lifespan: startup: cors origins ['http://localhost:3000', 'http://127.0.0.1:5500']
...
10:14:41 INFO [-] api.lifespan: shutdown: releasing resources
```

Once each. Everything before the `yield` runs at startup, everything after at shutdown. This replaces
the deprecated `@app.on_event("startup")` pair, and it is better because setup sits next to its own
teardown. It is where module 11 opens a connection pool and module 10 creates an HTTP client.

`TestClient` only triggers lifespan when used as a context manager. Calling `TestClient(app)` without
`with` means startup never runs - a silent trap when a test depends on something created there.

## Why It Is Done This Way

**Why CORS is outermost.** So its headers land on every response, including errors produced further
in. A 500 without CORS headers is invisible to the browser client.

**Why `cors_allowed_origins` is typed `str` and split by hand.** `pydantic-settings` tries to parse a
`list[str]` field from the environment as JSON, so a comma-separated `.env` value fails with a
`JSONDecodeError` that does not mention lists or CORS. A `str` field plus a property keeps the `.env`
readable.

**Why `allow_origins` is an explicit list and not `["*"]`.** A wildcard is incompatible with
`allow_credentials=True` - browsers reject that combination outright. It is also a bad default: any
site could then make credentialed requests on a logged-in user's behalf.

**Why the request id is validated before being echoed.** It goes into a response header and into the
logs. Unvalidated, that is header injection plus unbounded log entries.

**Why the timing is measured with `perf_counter`.** It is a monotonic clock. `time.time()` can move
backwards when the system clock is adjusted, which produces negative durations.

**Why the ContextVar token is reset in a `finally`.** Without it the value leaks into whatever task
reuses the context, and a later unrelated request logs a stale id.

## Known Gaps

- Logging is still plain text. Structured JSON, which is what a log aggregator needs, is module 16.
- No rate limiting. That arrives in module 17, where the endpoint being protected is expensive.
- The access log duplicates uvicorn's own. In production one of the two should be turned off.
- `GZipMiddleware` compresses per response with no caching. Fine here, worth measuring under load.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8, Starlette 1.3.1.

```
=== lifespan ===
startup logged once, shutdown logged once

=== every response carries both headers ===
200/404/422/500/503 + /docs + unmatched route + 405   all have x-request-id and x-response-time-ms

=== the 500 path ===
before fix: x-request-id None, timing None, CORS None, body reference "-"
after fix : x-request-id c836cb79d365, timing 2.78, CORS http://localhost:3000,
            body reference c836cb79d365, header == body: True

=== inbound request id ===
valid honoured; too short / too long / illegal chars / CRLF injection all replaced

=== timing ===
slept 0/120/400ms -> reported 0.36 / 121.13 / 401.30 ms

=== gzip ===
identity 140701 bytes -> gzip 2628 bytes; small responses left uncompressed

=== CORS ===
allowed origin   -> allow-origin set, expose-headers: x-request-id, x-response-time-ms
disallowed       -> 200 served, allow-origin absent, browser blocks
preflight        -> 200, methods/headers/max-age correct, no request id (short-circuited)
errors           -> 404, 503, unmatched-404 and 500 all carry allow-origin

=== real browser, 127.0.0.1:5500 -> 127.0.0.1:8000 ===
GET  /health        200, JS read both custom headers, client id honoured end to end
GET  /products/boom 500, JS read the error body
POST /products      201, preflighted correctly
console errors: none
```

## What I Learned

- `ServerErrorMiddleware` sits outside every middleware the application registers, so an unhandled
  exception produces a response that has never been through CORS, never been given a request id, and
  never been timed. Nothing in the source suggests this. It only appeared because the 500 case was
  measured rather than assumed, and it is the kind of bug that reaches production and then presents
  as an unreproducible browser problem.
- CORS is enforced by the browser, not by the server. A rejected origin still gets its request
  executed; only the response is withheld from JavaScript. `curl` is unaffected. Treating CORS as an
  access control is a serious misunderstanding.
- `expose_headers` is required for JavaScript to read any custom response header. Without it the
  header is on the wire, visible in devtools, and `null` from `fetch()`.
- Any custom request header makes a request non-simple and triggers a preflight. Sending
  `X-Request-ID` on a GET doubled the number of HTTP round trips.
- `BaseHTTPMiddleware` runs the downstream app in a separate task, so a `ContextVar` set in it does
  not reliably reach the endpoint. Pure ASGI middleware avoids this, at the cost of having to edit
  headers on the raw `http.response.start` message.
- A `logging.Filter` that always returns `True` is not filtering, it is decorating. It is the
  documented way to inject a computed field into every record without touching any call site.
- `TestClient` only runs lifespan when used as a context manager. Without `with`, startup silently
  never happens.
- Middleware registration order is inside-out, and getting it wrong produces no error at all - just
  headers that are quietly missing from some responses.

## Navigation

[Previous](../06-error-handling/) | [All modules](../README.md) | [Next](../08-crud-and-testing/)
