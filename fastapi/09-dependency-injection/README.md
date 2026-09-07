# 09 - Dependency Injection

## What This Project Does

Takes the module 08 task manager and moves everything repeated across handlers into a dependency
toolkit: pagination, store access, 404 resolution, a request-scoped logger, a unit of work with real
teardown, and two guards.

Then it does the thing dependencies exist for - replaces every one of them in tests with
`dependency_overrides`, without touching a line of production code.

**94 tests.** The behaviour tests from module 08 are carried over unchanged, so the refactor can be
shown not to have altered what the API does.

## Topics Covered

- `Depends()` and how FastAPI resolves the dependency graph
- Function dependencies and class dependencies
- Sub-dependencies, and dependencies that consume path parameters
- Router-level and application-level dependencies
- `yield` dependencies: setup, teardown, commit and rollback
- Per-request dependency caching, and `use_cache=False`
- Dependency resolution order, and what it decides
- `dependency_overrides` for testing

## Project Layout

```
09-dependency-injection/
|-- dependencies.py            the subject of this module
|-- main.py                    app, app-level dependency, middleware
|-- config.py                  Settings, usable directly as a dependency
|-- store.py schemas.py        carried from module 08
|-- errors.py handlers.py      carried from module 06
|-- middleware.py context.py   carried from module 07
|-- routers/
|   |-- tasks.py               8 routes, refactored onto the toolkit
|   |-- admin.py               2 routes, guarded at the router
|   |-- diagnostics.py         8 routes that make the machinery observable
|-- tests/
    |-- conftest.py            fixtures + FakeStore
    |-- test_dependencies.py   55 tests, the mechanics
    |-- test_overrides.py      16 tests, dependency_overrides
    |-- test_tasks.py          23 tests, carried from module 08 unchanged
```

## How to Run

```bash
uvicorn main:app --reload
```

```bash
pytest
```

The admin routes need a key. It is `ADMIN_API_KEY` in the shared root `.env`:

```bash
curl -H "X-API-Key: dev-admin-key-2f8c41ba97e5" http://127.0.0.1:8000/admin/stats
```

## What the Refactor Removed

Module 08, every one of five handlers:

```python
def update_task(task_id: TaskId, payload: TaskUpdate) -> dict:
    _require(task_id)
    changes = payload.model_dump(exclude_unset=True)
    return store.update(task_id, changes)
```

Module 09:

```python
def update_task(task: TaskDep, payload: TaskUpdate, store: StoreDep, uow: UnitOfWorkDep) -> dict:
    return store.update(task["id"], payload.model_dump(exclude_unset=True))
```

The lookup, the 404, the store import and the transaction are all gone from the body. The signature
now states what the handler needs; the body does only what the handler is for.

## How It Works

### Pagination as a class dependency

```python
class PaginationParams:
    def __init__(self, limit: Annotated[int, Query(ge=1, le=100)] = 20,
                 offset: Annotated[int, Query(ge=0)] = 0) -> None: ...
    def page_of(self, items: list) -> dict: ...
```

A class is callable, so FastAPI inspects `__init__` and turns its parameters into query parameters
exactly as it would for a function. A class rather than a function because pagination is two values
*plus* the behaviour that goes with them - `page_of()` builds the envelope, including the pre-slice
total, so no endpoint repeats that arithmetic.

Used by four endpoints across two routers. The constraints are declared once:

```
16 assertions from one declaration:
  4 endpoints x 4 bad inputs (limit=0, limit=500, offset=-1, limit=abc) -> all 422
  4 endpoints -> identical envelope keys, identical defaults
```

A fifth paginated endpoint inherits all of it by adding one parameter.

### A sub-dependency that resolves the path

```python
def get_task_or_404(task_id: int, store: StoreDep) -> dict:
    task = store.get(task_id)
    if task is None:
        raise NotFoundError(f"No task with id {task_id}")
    return task
```

It depends on another dependency and reads the path parameter itself. Five endpoints now receive a
task that is guaranteed to exist:

```
GET    /tasks/999          404  "No task with id 999"
PUT    /tasks/999          404  "No task with id 999"
PATCH  /tasks/999          404  "No task with id 999"
DELETE /tasks/999          404  "No task with id 999"
POST   /tasks/999/complete 404  "No task with id 999"
```

One message, one implementation, five endpoints, and none of them contains a lookup.

### Per-request caching, measured

```
GET /diagnostics/cache      {"a":"a:shared-value","b":"b:shared-value","shared_calls":1}
GET /diagnostics/cache-off  {"a":..,"b":..,"c":"c:shared-value","shared_calls":2}
```

`shared_subdependency` is reached twice in the first graph and executed **once**. FastAPI caches a
dependency's result for the duration of one request. Adding a third consumer declared with
`use_cache=False` raises the count by exactly one.

This is what makes a `get_current_user` dependency cheap to depend on everywhere in module 12 - it
runs once per request no matter how many things ask for it.

The cache does not survive between requests; two consecutive calls both report `1`.

### yield teardown, and its ordering

```
GET /diagnostics/nested
response body says: events_so_far = ["outer.setup", "inner.setup"]
EVENTS after the response:  ["outer.setup", "inner.setup", "inner.teardown", "outer.teardown"]
```

Teardown is last-in-first-out, and it has not run when the endpoint body executes. The tests assert
against a module-level `EVENTS` list rather than the response body, because by definition the
teardown happens after the body is produced.

### The unit of work, and which failures roll back

```python
try:
    yield uow
except Exception:
    uow.rollback()
    raise
else:
    uow.commit()
finally:
    uow.close()
```

Measured across every failure type:

```
success (200)                  uow.begin -> uow.commit   -> uow.close
unhandled exception (500)      uow.begin -> uow.rollback -> uow.close
deliberately raised 404        uow.begin -> uow.rollback -> uow.close
conflict 409                   uow.begin -> uow.rollback -> uow.close
invalid request body 422       uow.begin -> uow.rollback -> uow.close
404 from an earlier dependency (uow never opened)
```

Two of those are worth stopping on.

**A deliberately raised 404 rolls back.** Not obvious either way from reading the code, and it is
the case that decides whether a request failing halfway leaves a partial write committed. It gets
its own test for that reason.

**A 404 raised by an earlier dependency never opens the transaction at all.** `get_task_or_404` is
declared before `uow` in the parameter list, and FastAPI resolves in order, so a request that cannot
proceed never starts a unit of work. That is a genuine benefit - and it would silently reverse if
someone reordered the parameters, with no error and no test failure unless one exists for it. There
is one.

**A body validation failure does open one.** Request body validation happens after dependencies are
solved, so an invalid payload opens a transaction that was never going to be used. Harmless because
it rolls back, and worth knowing before wondering why a database shows transactions from requests
that returned 422.

### Router-level and application-level dependencies

```python
router = APIRouter(prefix="/admin", dependencies=[Depends(verify_api_key)])
```

No admin endpoint mentions the API key. The guard is declared once, so a route added later is
protected by default rather than by whoever adds it remembering.

```
GET /admin/tasks  (no key)        401
GET /admin/tasks  (wrong key)     401
GET /admin/tasks  (correct key)   200
GET /tasks        (no key)        200   <- unaffected
```

The 401 comes back in the standard error envelope, because `UnauthorisedError` subclasses `AppError`
and the module 06 handlers pick it up with no new code.

`dependencies=[Depends(record_request)]` on `FastAPI()` runs for every route on the application,
including `/docs` and `/openapi.json`. Useful for something genuinely universal - and only for that,
for the same reason.

A dependency used for its side effect returns nothing and is attached with `dependencies=[...]`
rather than as a parameter, so no endpoint carries an argument it never reads.

### dependency_overrides

The reason to route everything through `Depends()` in the first place.

```python
app.dependency_overrides[get_store] = lambda: fake_store
```

```
GET /tasks -> {"total": 2, "items": ["Fake task one", "Fake task two"]}
```

Three properties worth noting, each with a test:

**The fake is not a subclass.** `FakeStore` implements three methods and inherits from nothing. The
seam is duck-typed, so a test double does not have to satisfy the real class's constructor.

**Overriding a parent replaces it everywhere in the graph.** `get_task_or_404` depends on
`get_store`; overriding `get_store` alone is enough for `GET /tasks/101` to find the fake task and
`GET /tasks/1` to 404.

**Overriding beats patching the cache.** `get_settings` is `lru_cache`d. Overriding the dependency
bypasses the cache for the request without touching it, so `get_settings()` called directly still
returns the real settings. Reaching for `get_settings.cache_clear()` instead would mutate global
process state for every other test in the session.

A class dependency is overridden the same way:

```python
app.dependency_overrides[PaginationParams] = lambda: PaginationParams(limit=1, offset=3)
```

### Override hygiene, demonstrated

Clearing `app.dependency_overrides` between tests is easy to forget and painful to debug, because a
leaked override fails whichever test runs *next*. The autouse fixture clears it. Removing both
clears and re-running:

```
no override clearing at all: 18 failed, 76 passed
    test_this_is_why_the_guard_returns_nothing
    test_the_real_settings_come_back_afterwards
    test_pagination_can_be_forced
    test_overrides_are_empty_at_the_start_of_every_test
    test_setting_an_override_does_not_leak_between_parametrized_runs[1]
    ...
restored                   : 94 passed
```

Eighteen tests, none of which are the test that set the override.

## Why It Is Done This Way

**Why `get_store()` exists at all when it just returns a module-level object.** It is the seam. An
endpoint that imports `store` directly cannot be given a different one. One line of indirection buys
every override test in the suite.

**Why `dependencies.py` is one module rather than dependencies living next to their routers.**
`PaginationParams` is used by two routers and `get_store` by three. Putting shared dependencies with
one of their consumers means the other consumers import across a boundary that says nothing.

**Why the `Annotated` aliases (`Pagination`, `StoreDep`, `TaskDep`).** `page: Pagination` reads
better than `page: PaginationParams = Depends(PaginationParams)` repeated in eight signatures, and
changing how a dependency is provided is then a one-line edit.

**Why `UnitOfWork` is fake rather than a real transaction.** Getting the rollback path right is
easier when the failure can be triggered on demand. The dependency's shape does not change in module
11; only the object it yields does.

**Why the diagnostics router exists.** Caching, teardown ordering and resolution order leave no
trace in a normal response. The alternatives were to assert nothing or to assert from reading the
FastAPI source. A real API would not ship these routes.

**Why `verify_api_key` returns `None`.** So it can be attached with `dependencies=[...]` and so a
test can replace it with `lambda: None`. Both follow from it having no return value.

**Why the module 08 behaviour tests were carried over unchanged.** A refactor is only safe if the
tests that describe the old behaviour still pass against the new implementation. They were not
edited; 23 of the 94 tests are module 08's, verbatim.

## Known Gaps

- `verify_api_key` is a single shared secret compared with `!=`. That is not constant-time and not
  per-user. Module 12 replaces it with JWT and `secrets.compare_digest`.
- Every dependency here is synchronous. `async def` dependencies behave identically from the caller's
  side; module 10 covers when that matters.
- No coverage measurement yet.
- `EVENTS` is a module-level list and is not concurrency-safe. It exists only to make teardown
  observable in tests.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8, pytest 9.1.1.

```
=== full suite ===
94 passed in 0.58s

=== order independence ===
normal order            94 passed
reversed order          94 passed
test_dependencies.py    55 passed
test_overrides.py       16 passed
test_tasks.py           23 passed

=== override hygiene is load-bearing ===
no clearing   18 failed, 76 passed
restored      94 passed

=== caching ===
two consumers, shared dependency     shared_calls = 1
plus one use_cache=False consumer    shared_calls = 2
two consecutive requests             1, then 1

=== yield teardown ===
nested:  outer.setup -> inner.setup -> inner.teardown -> outer.teardown
body sees only:  ["outer.setup", "inner.setup"]

=== unit of work ===
200  begin -> commit   -> close
500  begin -> rollback -> close
404 raised in endpoint    begin -> rollback -> close
409  begin -> rollback -> close
422 body validation       begin -> rollback -> close
404 from earlier dependency   never opened

=== router guard ===
no key 401 | wrong key 401 | correct key 200 | non-admin routes unaffected
401 uses the standard envelope; every admin route documents 401 in OpenAPI

=== pagination reuse ===
4 endpoints, 2 routers, identical envelope, identical defaults,
16 validation assertions from one __init__
```

## What I Learned

- Dependency declaration order decides real behaviour. Putting `get_task_or_404` before the unit of
  work means a 404 never opens a transaction. Swapping two parameters would reverse that with no
  error and no failing test - unless one exists for it, which is why one does.
- A deliberately raised 404 rolls back a `yield` dependency just as an unhandled exception does. I
  could not tell from reading the code which way it went, which is exactly the signal that it needed
  measuring rather than assuming.
- Body validation runs *after* dependencies are solved, so a malformed payload still opens and rolls
  back a transaction. Obvious in hindsight, invisible until measured.
- Per-request caching is what makes fine-grained dependencies affordable. Without it, a
  `get_current_user` used by five sub-dependencies would run five times per request.
- `dependency_overrides` works on any node at any depth, and the double does not need to be a
  subclass. Replacing `get_store` also replaced it inside `get_task_or_404`, which is what makes the
  technique scale past trivial cases.
- Overriding a dependency is better than clearing an `lru_cache`, because it is scoped to the
  request rather than to the process.
- Forgetting to clear `dependency_overrides` breaks 18 tests, none of which are the one at fault.
  That failure mode is the strongest argument for putting the cleanup in an autouse fixture rather
  than trusting each test.
- A dependency returning `None` is not a degenerate case. It is what enables router-level attachment
  and a one-line test override.

## Navigation

[Previous](../08-crud-and-testing/) | [All modules](../README.md) | [Next](../10-async-and-concurrency/)
