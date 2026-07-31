# 01 - Hello FastAPI

## What This Project Does

The smallest useful FastAPI application. It exposes a root endpoint returning a welcome message and
a `/health` endpoint reporting service status. The real point of the module is not the two
endpoints - it is seeing that FastAPI generated a complete, interactive API documentation site from
nothing but the function signatures.

## Topics Covered

- Installing FastAPI and Uvicorn
- ASGI vs WSGI, and why FastAPI is not Flask
- Creating the application instance and setting its metadata
- Defining an endpoint with a route decorator
- Automatic documentation: Swagger UI, ReDoc, and the OpenAPI schema
- The `--reload` development loop

## How to Run

Dependencies are installed once into the shared `.venv` at the repository root - see the
[root README](../README.md). Activate it, then from inside this folder:

```bash
uvicorn main:app --reload
```

Then open:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Raw schema: http://127.0.0.1:8000/openapi.json

Stop the server with `Ctrl+C`.

## Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/` | Welcome message | `{"message": "Welcome to the FastAPI learning journey"}` |
| GET | `/health` | Service health check | `{"status": "ok", "version": "0.1.0"}` |

## How It Works

### The run command

`uvicorn main:app --reload` breaks down as:

- `uvicorn` - the ASGI server that actually listens on a TCP port
- `main` - the module, meaning `main.py`
- `app` - the variable inside that module holding the `FastAPI()` instance
- `--reload` - watch the files and restart on save

FastAPI itself is a framework, not a server. It does not open a socket. Uvicorn does that and hands
each request to the FastAPI application. This is why two separate packages are needed.

### ASGI, and why it matters

Flask and Django's traditional stack are WSGI. WSGI is synchronous by design: one worker handles one
request at a time, start to finish. If that request spends two seconds waiting on a database or an
external API, the worker sits idle for two seconds.

ASGI is the asynchronous successor. A single worker can start a request, and while that request is
waiting on something external, pick up another. For an API whose main job is waiting on a database
or an LLM provider, this is a large difference. That is the reason FastAPI exists, and it is
explored properly in module 10.

### Where the documentation comes from

Nothing in `main.py` writes any documentation. FastAPI inspects the code at startup:

- the decorator gives it the method and path
- the function name and docstring give it the summary and description
- the `tags` argument groups the endpoint
- the return type annotation gives it the response shape
- the `title`, `description`, and `version` on `FastAPI()` give it the page header

From that it builds an OpenAPI document, served at `/openapi.json`. `/docs` and `/redoc` are just
two different JavaScript viewers pointed at that same document. The schema is the real artifact; the
two pages are views of it.

This is worth internalising early: in FastAPI, the type annotations are not optional hints for a
linter. They are the source of truth for validation and documentation both.

## Why It Is Done This Way

**Why a `/health` endpoint in a two-endpoint app.** It looks redundant here, but a health endpoint is
a hard requirement the moment anything else needs to know whether the process is alive - Docker
health checks, a load balancer, an uptime monitor. It should be cheap and dependency-free, so that
it answers "is the process running" rather than "is the entire system healthy". Adding it now
establishes the habit.

**Why `tags` on both routes.** With two endpoints it changes nothing. By module 11 there will be
dozens, and Swagger UI without tags is an unusable flat list. Cheap to add now, expensive to
retrofit.

**Why `def` and not `async def`.** Neither endpoint does any I/O, so there is nothing to await.
FastAPI runs a plain `def` endpoint in a threadpool, which is correct here. Writing `async def` for
a function containing no `await` gains nothing and, if blocking code is later added to it, actively
causes harm. The full rule is module 10.

**Why pinned versions in the shared `requirements.txt`.** `fastapi==0.140.8` rather than `fastapi`.
FastAPI is pre-1.0 and its minor releases have broken things before. A pinned file means this
project still runs in six months, which unpinned cannot promise.

## What I Learned

- FastAPI and the server are separate concerns. `uvicorn main:app` is naming a Python variable, not
  a file path, which is not obvious the first time.
- `/docs` is not a feature that was switched on. It is a rendering of `/openapi.json`, and that
  schema is generated purely from the function signatures. Reading the raw JSON made the mechanism
  clear in a way the pretty page did not.
- The 404 for an unknown path is produced by Starlette's router before any of my code runs. Almost
  everything FastAPI does happens around the endpoint function, not inside it.

## Verification

Confirmed working with Python 3.12.0, FastAPI 0.140.8, Uvicorn 0.51.0:

```
GET /            -> 200  {"message":"Welcome to the FastAPI learning journey"}
GET /health      -> 200  {"status":"ok","version":"0.1.0"}
GET /docs        -> 200
GET /redoc       -> 200
GET /openapi.json-> 200
GET /nope        -> 404
```

## Next

[Module 02 - Routing and APIRouter](../02-routing/)
