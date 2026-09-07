# 10 - Async and Concurrency

## What This Project Does

An aggregator that calls three slow upstream services and combines the result, written twice -
sequentially and concurrently - so the difference can be measured rather than argued about.

Alongside it, the same 200ms of work written four ways, to answer the question this module exists
for: **when does `async def` help, when does it do nothing, and when does it make things
catastrophically worse?**

Every number below was measured against a real uvicorn server, not estimated.

## Topics Covered

- `async def` vs `def`, and what FastAPI does with each
- The event loop, and what "blocking" actually means
- The threadpool that sync endpoints run in, and its limits
- `httpx.AsyncClient`, created once in lifespan
- `asyncio.gather`, and `return_exceptions=True`
- `run_in_threadpool` for unavoidable blocking work
- Why threads do not help CPU-bound Python
- Timeouts, and a case where the obvious one does not fire

## Project Layout

```
10-async-and-concurrency/
|-- upstream.py                a separate ASGI app: three deliberately slow services
|-- clients.py                 the shared AsyncClient, opened and closed in lifespan
|-- services.py                sequential / concurrent / resilient aggregation
|-- routers/aggregate.py       4 routes
|-- routers/blocking.py        the same work written four ways, plus CPU variants
|-- main.py config.py schemas.py
|-- errors.py handlers.py middleware.py context.py logging_config.py   carried forward
|-- tests/
    |-- conftest.py            a sync client and an async client, for different jobs
    |-- test_aggregate.py      20 tests
    |-- test_concurrency.py    11 tests, all timing based
```

## How to Run

```bash
uvicorn main:app --reload
```

```bash
pytest
```

By default the upstream services run in-process through `httpx.ASGITransport` - real httpx calls,
real concurrency, no socket. To run the upstream as a separate server over real HTTP:

```bash
uvicorn upstream:app --port 8011
```

then set `UPSTREAM_BASE_URL=http://127.0.0.1:8011`. The application code is identical either way;
only the transport changes.

## The Headline Measurement

Three upstream services: pricing 300ms, inventory 200ms, reviews 250ms. Sum 750ms, max 300ms.

```
sequential  runs=[763, 785, 786]  median=785.0ms
concurrent  runs=[313, 313, 311]  median=313.0ms

speedup: 2.51x   (780ms -> 310ms)
```

The sequential version is correct, idiomatic-looking async code:

```python
pricing   = await fetch(client, f"/pricing/{sku}")
inventory = await fetch(client, f"/inventory/{sku}")
reviews   = await fetch(client, f"/reviews/{sku}")
```

Every call is awaited before the next starts, so the total is the sum. `async` on its own buys
nothing. Overlapping the waits is what buys something:

```python
pricing, inventory, reviews = await asyncio.gather(
    fetch(client, f"/pricing/{sku}"),
    fetch(client, f"/inventory/{sku}"),
    fetch(client, f"/reviews/{sku}"),
)
```

The precondition is that the three calls do not depend on each other. `gather` cannot help when the
second request needs the first one's answer.

## The Trap

Ten concurrent requests, each doing 200ms of work. Ideal is ~200ms, fully serialised is ~2000ms.

```
async + asyncio.sleep         189ms     0.9x one request   overlapped
def   + time.sleep            208ms     1.0x one request   overlapped
async + run_in_threadpool     208ms     1.0x one request   overlapped
async + time.sleep           2013ms    10.1x one request   SERIALISED
```

The last one is a 10x slowdown from a one-word difference. `time.sleep` does not yield to the event
loop, so for its whole duration the coroutine holds the loop and nothing else runs.

Nothing warns about this. It passes review, it passes a single-request test, and it fails only under
concurrency.

Note the second row: **a plain `def` endpoint is not the slow option.** FastAPI runs it in a worker
thread, so blocking there blocks that thread and not the loop. For blocking code, `def` is the
correct choice, and wrapping the same body in `async def` makes it dramatically worse.

### The consequence that actually matters

The slowdown above is bad. This is worse. During a single 1500ms request, an unrelated `/health`
call was timed:

```
async + asyncio.sleep      worst health probe      2.7ms   loop free
def   + time.sleep         worst health probe      2.6ms   loop free
async + run_in_threadpool  worst health probe      2.4ms   loop free
async + time.sleep         worst health probe   1474.9ms   LOOP BLOCKED
    probes: [1474.9, 1.6, 1.8, 2.1, 1.9, 2.0, 1.8, 1.5]
```

`/health` does nothing and touches nothing that endpoint touches. It took 1.47 seconds because the
event loop was not free to run it. **One bad endpoint takes the entire server down for its
duration** - every route, every user, and the health check a load balancer uses to decide whether
the process is alive.

## The Rule

```
Does the endpoint body await anything?
  yes -> async def
  no, and it blocks (sync DB driver, requests, file I/O, time.sleep)
       -> def, and let FastAPI use the threadpool
  no, and it is trivial
       -> either; def is the safer habit

Must it be async def but also call blocking code?
  -> await run_in_threadpool(blocking_fn, ...)

Is the work CPU-bound?
  -> neither helps much. See below.
```

The single worst thing to do is write `async def` around a body containing no `await`. It gains
nothing when the body is fast, and it is a server-wide outage when the body blocks.

## The Threadpool Has a Ceiling

```
worker threads available: 40
 10 concurrent def requests ->  209ms  (1.0 batches of 200ms)
 40 concurrent def requests ->  233ms  (1.2 batches of 200ms)
 80 concurrent def requests ->  448ms  (2.2 batches of 200ms)
```

Up to the pool size, requests overlap. Beyond it they queue. So a slow `def` endpoint is still a
scalability limit - just a much higher one than blocking the loop, and one that degrades gradually
rather than catastrophically.

## Threads Do Not Parallelise CPU Work

```
one CPU request (threadpool): 66ms

8 concurrent  def   (threadpool)   529ms    8.0x one request
8 concurrent  async (event loop)   503ms    7.6x one request
```

Both are essentially serial. The GIL only lets one thread execute Python bytecode at a time, so
offloading CPU-bound work to a thread moves it without parallelising it. Compare with the I/O case,
which overlapped 10 requests into 1.0x.

This is the limit of `run_in_threadpool`, and it is worth knowing before module 12: bcrypt is
deliberately expensive and behaves exactly like this. Genuine CPU parallelism needs a process pool
or a separate service.

## A Timeout That Did Not Fire

The client is configured with a 2 second timeout. The endpoint asks the upstream for a 4 second
delay. Measured:

```
status 200   elapsed 4191ms
{"sku":"HP-2200","price":249.0,...}
```

The timeout never fired. `httpx`'s timeout is a **socket** timeout, and `ASGITransport` has no
socket - there is nothing to time out on, so the call ran to completion.

Over real HTTP the httpx timeout would have worked. But relying on it alone means the guarantee
depends on the transport, which is a fragile thing for a guarantee to depend on. Wrapping the await
itself holds regardless:

```python
async with asyncio.timeout(budget):
    response = await client.get(...)
```

After:

```
status 504   elapsed 2210ms
{"error":{"code":"upstream_unavailable","message":"The pricing service did not respond within 2.0s",...}}
```

504 rather than 503, because the distinction is useful: a service that is down may return in
seconds, whereas one that is merely slow will probably be slow again on an immediate retry.

There is a regression test asserting both the status and that it fails in under 3.5 seconds.

## Partial Failure

`asyncio.gather` is all-or-nothing by default: one failure cancels the siblings and the whole
endpoint fails. That is rarely what a page assembling several independent panels wants.

```
all healthy   -> 200  failed=[]
reviews down  -> 200  failed=[{'service': 'reviews', 'error': 'HTTPStatusError'}]
                 pricing present: True, reviews: None
```

`return_exceptions=True` turns it into best-effort. Which behaviour is right is a product decision,
not a technical one - a price is probably essential, a review count probably is not. A test also
asserts the failing sibling does not slow the survivors down.

## How It Works

### One client, created in lifespan

```python
async def lifespan(app):
    await open_client(settings)
    yield
    await close_client()
```

Creating an `AsyncClient` per request is the most common performance mistake in async Python. Each
new client gets its own connection pool, so every call pays for a TCP handshake and a TLS
negotiation that a reused client would have skipped. This is what module 07's lifespan section was
building towards.

`get_client()` raises a message naming its own cause when the client is missing, because forgetting
`with TestClient(app)` is the easiest mistake to make here and the default failure would be an
`AttributeError` on `None`.

### A real upstream, not a simulated one

`upstream.py` is a separate ASGI application. The aggregator reaches it through a real `httpx`
client, so the concurrency measured is genuine rather than three `asyncio.sleep` calls dressed up as
network calls. `ASGITransport` awaits the app the same way a network transport awaits a socket, so
tests are fast and deterministic without replacing httpx with a mock - the code under test is the
code that runs in production.

### Two test clients, for different jobs

`TestClient` is synchronous. It cannot issue two overlapping requests, so every concurrency
assertion written against it would pass for the wrong reason. The timing tests use a real
`httpx.AsyncClient` driving the app from the test's own event loop.

`ASGITransport` does not run lifespan events, so the async fixture calls `open_client` and
`close_client` by hand.

## Measuring an Event Loop From Inside It

The loop-blocking test failed on the first attempt, and the reason is worth recording because the
test was wrong rather than the code.

The obvious probe is: start the slow request, sleep briefly, then time a `/health` call.

```
AssertionError: health took only 1ms - expected blocking
```

In-process, the test shares the event loop it is trying to observe. The brief sleep is itself
blocked by the endpoint, so it resumes only *after* the blocking work has finished, and the health
call is timed against a loop that is now free. Every variant looks fast.

The fix is to avoid depending on the loop being measured: take one timestamp before anything is
scheduled, run both requests together, and record when each *completes*.

```python
start = time.perf_counter()

async def run(target):
    await aclient.get(target)
    return target, (time.perf_counter() - start) * 1000

finished = dict(await asyncio.gather(run(path), run("/health")))
```

The real-server benchmark did not have this problem, because the measuring process and the blocked
loop were different processes.

## Why It Is Done This Way

**Why the upstream is a separate ASGI app rather than routes on the main one.** Calling itself would
make the measurements ambiguous: a blocked loop would also block the upstream, and the numbers would
be measuring two things at once.

**Why `elapsed_ms` is in the response body.** Server-measured, so it excludes client and network
overhead. The `X-Response-Time-Ms` header from module 07 measures the whole request; this measures
just the aggregation.

**Why `break_reviews` is a parameter rather than monkeypatching the module.** The first version
swapped `services.fetch` at request time and restored it in a `finally`. That is a process-global
mutation to serve one request, and under concurrency two requests would corrupt each other. Passing
it down keeps the failure injection local to one call.

**Why timing tests use wide margins.** They distinguish "overlapped" from "serialised", which are an
order of magnitude apart. A test asserting 200ms rather than 210ms would fail on a loaded machine
and teach nothing.

**Why there is a `@pytest.mark.timing` marker.** These tests take 15 seconds and are the ones most
likely to be flaky on shared CI. Marking them means they can be excluded with `-m "not timing"`
without hunting for them.

## Known Gaps

- One uvicorn worker throughout. Multiple workers change the threadpool arithmetic, since each
  process gets its own pool. Module 16.
- No `ProcessPoolExecutor` for the CPU case. The measurement shows the problem; the fix is out of
  scope here.
- No retry or backoff on upstream failure. `tenacity` is installed for module 17.
- No connection pool tuning. httpx defaults are used as they come.
- No structured timing metrics. `elapsed_ms` in a body is a demonstration, not observability.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8, httpx 0.28.1, on a real uvicorn server.

```
=== test suite ===
31 passed in 15.27s
reversed order        31 passed
test_aggregate.py     20 passed
test_concurrency.py   11 passed

=== aggregation ===
sequential  median 785.0ms      concurrent  median 313.0ms      speedup 2.51x

=== 10 concurrent requests, 200ms of work each ===
async + asyncio.sleep       189ms   overlapped
def   + time.sleep          208ms   overlapped
async + run_in_threadpool   208ms   overlapped
async + time.sleep         2013ms   SERIALISED (10.1x)

=== /health latency during one 1500ms request ===
async + asyncio.sleep         2.7ms   loop free
def   + time.sleep            2.6ms   loop free
async + run_in_threadpool     2.4ms   loop free
async + time.sleep         1474.9ms   LOOP BLOCKED

=== threadpool ===
capacity 40 threads
10 concurrent -> 209ms | 40 -> 233ms | 80 -> 448ms

=== CPU-bound, 8 concurrent ===
def   (threadpool)  529ms  8.0x one request
async (event loop)  503ms  7.6x one request

=== resilience and timeouts ===
all healthy    200  failed=[]
reviews down   200  failed=[{'service':'reviews','error':'HTTPStatusError'}]
4s upstream, 2s budget:  before asyncio.timeout  200 in 4191ms
                         after                   504 in 2210ms
```

## What I Learned

- `async` alone buys nothing. The sequential aggregator is fully async, fully awaited, and exactly
  as slow as blocking code. Overlapping the waits is the entire benefit, and it has to be asked for.
- A plain `def` endpoint is not the slow choice. It runs in a threadpool and overlapped 10 requests
  as well as the async version did. For blocking code it is the *correct* choice, and this is the
  opposite of what "async is faster" suggests.
- One blocking call inside one `async def` endpoint made an unrelated `/health` check take 1.47
  seconds. The blast radius is the whole process, not the endpoint.
- httpx's timeout is a socket timeout. Over `ASGITransport` it never fires, and a 4-second call
  returned 200 against a 2-second budget. `asyncio.timeout` wraps the await and holds regardless of
  transport, which makes it worth having even when the client timeout would also work.
- The threadpool has 40 threads by default, so `def` endpoints have a ceiling too - just a much
  higher and gentler one than blocking the loop.
- Threads do not parallelise CPU-bound Python. 8 concurrent hashing requests took 8x a single one in
  the threadpool, essentially the same as on the event loop. `run_in_threadpool` is for I/O.
- Measuring an event loop from code running on that same loop does not work. The first version of
  the blocking test measured the loop *after* it had been freed and reported everything as fast. The
  fix was to stop depending on the thing being measured.
- `asyncio.gather` returns results in argument order, not completion order. Easy to assume otherwise
  when unpacking three results from three calls of different durations.

## Navigation

[Previous](../09-dependency-injection/) | [All modules](../README.md) | [Next](../11-database/)
