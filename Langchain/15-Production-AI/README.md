# Module 15 - Production AI

**Status:** API complete, 17 automated checks passing, streaming verified.
The Dockerfile is written but **not built**, because Docker Desktop was not
running on this machine. See the honest note at the end.

## Goal

Put a LangChain chatbot behind an HTTP API, with the things a service needs that
a script does not.

## Topics covered

| Topic | Where it appears |
|-------|------------------|
| FastAPI | `app.py` |
| Streaming | `POST /chat/stream` |
| Logging | request id middleware, structured log lines |
| Authentication | `require_api_key` |
| Docker | `Dockerfile`, `.dockerignore`, `requirements-api.txt` |
| LangSmith | environment variables, below |

## Files

| File | Purpose |
|------|---------|
| `app.py` | The API. Four endpoints. |
| `test_api.py` | 14 free checks, plus 3 more with `--live`. |
| `Dockerfile` | Container build. |
| `requirements-api.txt` | Only what the API imports, not the whole course. |

## Running it

```powershell
uvicorn app:app --reload --port 8000
```

Then open http://localhost:8000/docs for the generated API documentation, which
FastAPI builds from the Pydantic models with no extra work.

```powershell
curl http://localhost:8000/health

curl -X POST http://localhost:8000/chat `
  -H "X-API-Key: local-dev-key" `
  -H "Content-Type: application/json" `
  -d '{\"message\": \"hello\"}'
```

## Testing without spending quota

```powershell
python test_api.py          # 14 checks, no model calls
python test_api.py --live   # adds 3 checks and one real call
```

```
free checks, no model calls
  ok    health returns 200
  ok    chat without a key is 401
  ok    chat with a bad key is 401
  ok    empty message is rejected
  ok    oversized message is rejected
  ok    out of range temperature is rejected
  ok    config leaks no secret
  ok    a supplied request id is echoed
  ...
14 passed, 0 failed
```

`TestClient` calls the app in process, so no port is opened and no model is
touched. **Auth, validation, error mapping and logging are all testable for
free**, and they are where most service bugs actually live. Keep the model out
of the test loop wherever you can.

## The endpoints

| Endpoint | Auth | Model call |
|----------|------|-----------|
| `GET /health` | no | **no** |
| `GET /config` | yes | no |
| `POST /chat` | yes | yes |
| `POST /chat/stream` | yes | yes |

### /health does not call the model, on purpose

A load balancer polls a health endpoint every few seconds. If that check called
the model it would burn the entire free quota on its own before a single user
arrived, and it would report the service unhealthy the moment the quota ran out,
which would take it out of rotation for a reason unrelated to whether it is
running.

Health checks answer "is this process alive", not "is every dependency perfect".

### /chat/stream

```
delta: 'Mercury: Smallest planet near the sun.\nVenus: Thick atmosphere'
delta: ' traps intense heat.\nEarth: Life thrives on this world...'
delta: ' gas giant with storms.\nSaturn: Famous for beautiful icy rings...'
delta: '.\nNeptune: Distant world with strong winds.'
done, request_id=96e6aaa1e9ab
```

Four chunks for a long answer. A short answer arrives in one, which is worth
knowing before concluding streaming is broken.

**Streaming changes error handling in a way that is easy to miss.** Once the
first chunk is sent, the response status is already 200. A failure after that
cannot become a 500, so it has to be reported inside the stream:

```python
except Exception as error:
    yield f"data: {json.dumps({'error': detail})}\n\n"
```

A client that only checks the status code will treat a failed stream as a
success. The `done` event exists for the same reason: it is how a client knows
the stream finished rather than the connection dropping.

## Turning provider errors into HTTP status codes

This is the difference between an API and a thin wrapper:

| Provider condition | Status | Why |
|--------------------|--------|-----|
| quota exhausted or rate limited | **429** with `Retry-After: 60` | the client should back off |
| model retired | 502 | upstream problem, not the caller's fault |
| upstream rejected the request | 502 | as above |
| service misconfigured | 503 | the deployment is wrong, not the request |
| anything else | 502 | do not leak internals |

A client seeing 429 with `Retry-After` knows what to do. A client seeing 500
knows only that something broke and will usually retry immediately, making it
worse.

The classification functions come straight from `common/errors.py`, written back
in Module 01 and reused unchanged. The error handling that started as friendlier
console messages turned out to be exactly what an API needs.

### Errors are logged in full and returned sanitised

```python
log.warning("model call failed: %s", str(error).splitlines()[0][:200])
raise http_error_for(error) from error
```

The provider's 429 contains project ids, quota metric names and internal
limits. That belongs in your logs, not in a response body a stranger reads.

## Authentication

`X-API-Key`, checked against `SERVICE_API_KEYS`.

**The service key is not the Gemini key.** The provider key stays on the server
and is never accepted from a caller, never returned, and never logged. `/config`
reports how many keys are configured, never their values, and a test asserts
that no response body contains `AIza`.

An LLM endpoint costs money per request, so an open one is not untidy, it is a
bill. This is the simplest thing that works; a real service would attach rate
limits to each client key.

## Logging

Every request gets an id, from the caller's `X-Request-ID` header if present, or
generated:

```
2026-07-29 17:41:02 INFO [96e6aaa1e9ab] POST /chat -> 200 in 1352ms
2026-07-29 17:41:02 INFO [96e6aaa1e9ab] chat ok model=gemini-3.1-flash-lite in=22 out=48
```

The id is returned in the response headers too, so a user reporting a problem
can quote something that finds the exact request. Honouring an incoming
`X-Request-ID` is what lets a trace span several services.

A `ContextVar` carries the id into log records without threading it through
every function.

Token counts are logged per request. Those numbers are your bill, and nobody
notices a cost regression without them.

## Docker

```powershell
docker build -f 15-Production-AI/Dockerfile -t ai-chat-api .
docker run -p 8000:8000 -e GOOGLE_API_KEY=... -e SERVICE_API_KEYS=... ai-chat-api
```

Build from the **repository root**, not this folder, because the image needs
`common/` too.

Five decisions worth copying:

**Only the dependencies the API imports.** `requirements-api.txt` has five
entries. The repository's `requirements.txt` has more than twenty, including
chromadb, FAISS, a reranker and PDF parsers, none of which `app.py` or `common/`
import. Shipping them would add hundreds of megabytes and widen the attack
surface for nothing.

This was verified rather than assumed: a clean virtual environment with only
`requirements-api.txt` installed imports `app.py` successfully.

**Dependencies before source.** Editing code then does not invalidate the cached
install layer, which is the single biggest thing you can do for rebuild speed.

**No secrets in the image.** Keys arrive as environment variables at run time.
`.dockerignore` excludes `.env` explicitly, because anything baked into an image
is readable by anyone who can pull it.

**A non-root user.** A process that does not need root should not have it.

**`PYTHONUNBUFFERED=1`.** Without it logs sit in a buffer, and a crashed
container looks like it said nothing at all.

## LangSmith

Tracing needs no code change, only environment variables:

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=langchain-learning
```

LangChain checks for these and sends traces automatically: every chain step,
every prompt actually sent, every token count, every latency. It is the tool for
the questions this course kept hitting, such as which retriever step was slow or
what the model really received.

It is not wired up here because it needs a separate account, and because the
point is that it is configuration rather than code. Two warnings if you enable
it: your prompts and responses leave your machine, which matters for anything
sensitive, and the free tier has its own trace limit.

## What was not verified

**The Docker image was not built.** Docker Desktop's daemon was not running:

```
ERROR: failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

The Dockerfile is written from the same reasoning as the rest of the module, and
its dependency claim is verified independently, but the build itself is
untested. Start Docker Desktop and run the build command above to confirm it.
Expect to fix something small; a Dockerfile that has never been built usually
has one thing wrong with it.

