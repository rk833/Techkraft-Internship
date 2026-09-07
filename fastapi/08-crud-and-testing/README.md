# 08 - CRUD Operations and Testing

## What This Project Does

A task manager API with the full set of CRUD operations, plus the first real test suite in this
repository: **91 tests** covering every endpoint's success path, every endpoint's failure path, and
the cross-cutting contract inherited from modules 06 and 07.

Testing starts here and applies to every module after it. Writing one test suite at the end of the
course teaches far less than writing eleven of them.

The suite immediately earned its keep: it found a credential leak in the module 06 error handler.
Details below.

## Topics Covered

- Full create, read, update, delete against a store
- REST resource design, and a state transition that is not a field edit
- PUT vs PATCH, and idempotency as a tested property
- `pytest`: test functions, classes, assertions, fixtures, `parametrize`, `monkeypatch`
- `conftest.py` and `autouse` fixtures
- FastAPI's `TestClient`, and the two ways it lies to you by default
- Test isolation, and proving it rather than hoping
- Contract tests for cross-cutting behaviour

## Project Layout

```
08-crud-and-testing/
|-- main.py                    app, middleware, lifespan
|-- store.py                   TaskStore class with reset(), the key to isolation
|-- schemas.py                 TaskCreate / TaskReplace / TaskUpdate / TaskRead + error envelope
|-- routers/tasks.py           7 routes
|-- errors.py handlers.py      carried from module 06, one security fix
|-- middleware.py context.py   carried from module 07
|-- config.py logging_config.py
|-- pytest.ini                 pythonpath, testpaths, markers
|-- tests/
    |-- conftest.py            fixtures: reset_store, client, raw_client, new_task
    |-- test_tasks_crud.py     32 tests, happy paths
    |-- test_tasks_errors.py   29 tests, failure paths
    |-- test_contract.py       30 tests, envelope + headers + openapi
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

Run the tests:

```bash
pytest
```

Useful variants:

```bash
pytest -v
```

```bash
pytest tests/test_tasks_errors.py -k conflict
```

```bash
pytest -m contract
```

## Endpoints

| Method | Path | Description | Success |
|--------|------|-------------|---------|
| GET | `/tasks` | List, filter, paginate | 200 |
| POST | `/tasks` | Create | 201 |
| GET | `/tasks/{id}` | Get one | 200 |
| PUT | `/tasks/{id}` | Replace entirely | 200 |
| PATCH | `/tasks/{id}` | Update some fields | 200 |
| POST | `/tasks/{id}/complete` | Mark done | 200 |
| DELETE | `/tasks/{id}` | Delete | 204 |
| GET | `/health` | Health check | 200 |

## The Test Suite Found a Real Bug

`test_the_500_response_leaks_nothing` raises an exception whose message contains a plausible
secret, then asserts the response does not contain it:

```python
def explode(self):
    raise RuntimeError("secret connection string postgres://user:pw@host/db")

monkeypatch.setattr(store_module.TaskStore, "list", explode)
text = raw_client.get("/tasks").text
assert "postgres://" not in text
```

First run:

```
FAILED tests/test_contract.py::TestErrorEnvelope::test_the_500_response_leaks_nothing
1 failed, 90 passed
```

The module 06 handler included `str(exc)` in the response when `debug` was on, described at the time
as a "deliberate development trade". It returned the connection string in full.

What makes this worth writing down is that the module 06 README already contained the argument
against it:

> Exception messages routinely contain SQL fragments, file paths, and occasionally credentials from
> a connection string.

The reasoning was correct and written down, and the code two paragraphs earlier did the opposite.
A careful read did not catch it. One test did.

The fix, applied to modules 06, 07 and 08, is to include the exception **type** and nothing else:

```json
{"field": null,
 "message": "Unhandled ZeroDivisionError. The traceback is in the server log.",
 "type": "ZeroDivisionError"}
```

A type name is a fixed identifier with nothing interpolated into it, so it cannot carry data.

## How It Works

### Isolation is a design decision in the source, not just in the tests

`store.py` is a class with an explicit `reset()`, rather than module-level dicts:

```python
@pytest.fixture(autouse=True)
def reset_store():
    store.reset()
    yield
    store.reset()
```

`autouse=True` means no test has to remember to ask for it.

Two tests in `TestIsolation` are written as a deliberate trap - each mutates the store and then
asserts a count only correct from a clean start. To confirm the fixture is load-bearing rather than
decorative, it was switched to `autouse=False` and the suite re-run:

```
without autouse reset: 9 failed, 82 passed
with autouse restored: 91 passed
```

Nine tests depend on it. A suite that passes for the wrong reason is worse than no suite, so this
was measured rather than assumed.

### Order independence, demonstrated

`conftest.py` reverses collection order when an environment variable is set:

```python
def pytest_collection_modifyitems(items):
    if os.environ.get("REVERSE_TESTS"):
        items.reverse()
```

```
normal order    91 passed in 0.42s
reversed order  91 passed in 0.43s

test_tasks_crud.py    32 passed
test_tasks_errors.py  29 passed
test_contract.py      30 passed
```

Each file also passes alone. A suite with hidden ordering dependencies fails one of those five runs.

### The two ways TestClient lies

```python
with TestClient(app) as test_client:      # lifespan runs
    ...
TestClient(app, raise_server_exceptions=False)   # 500s are returned, not raised
```

Both defaults hide things. Without `with`, startup and shutdown never run, so anything created in
`lifespan` is absent and the failure looks unrelated to the cause. Without
`raise_server_exceptions=False`, an unhandled exception is re-raised into the test instead of
becoming a response, so the catch-all handler and every middleware around it are never exercised.

It is entirely possible to write a green suite that has never once run the 500 path. Both are
provided as separate fixtures so the choice is explicit.

### parametrize instead of loops

```python
@pytest.mark.parametrize("method,path", [
    ("get", "/tasks/999"), ("put", "/tasks/999"), ("patch", "/tasks/999"),
    ("delete", "/tasks/999"), ("post", "/tasks/999/complete"),
])
def test_missing_task_returns_404(self, client, method, path):
```

Five separate tests, five separate names in the report. A `for` loop inside one test would stop at
the first failure and report a single name, so the other four failures stay hidden until the first
is fixed.

### monkeypatch for the unreachable path

There is no request that makes `store.list()` fail. `monkeypatch` replaces it for the duration of
one test and undoes itself afterwards, with no teardown code and no risk of leaking into the next
test. It is how the 500 path gets tested at all.

### Idempotency as an assertion

```python
def test_is_idempotent(self, client):
    first = client.put("/tasks/2", json=payload).json()
    second = client.put("/tasks/2", json=payload).json()
    first.pop("updated_at"); second.pop("updated_at")
    assert first == second
```

`updated_at` is popped because it legitimately changes; everything else must not. This is the
property that distinguishes PUT from POST, and it is easy to break by generating something new
inside the handler, so it gets an explicit test rather than a comment.

The complementary PUT test asserts the destructive half:

```
before: tags == ["docs", "fastapi"]
PUT /tasks/1 {"title": "Replaced"}
after:  tags == [], priority == medium, description == None
```

### Contract tests

`test_contract.py` asserts cross-cutting properties that no per-endpoint test can:

- The error envelope has identical keys across six different failure modes
- `error.reference` equals the `X-Request-ID` header on every one of them
- Every response carries a request id and a timing header
- An unsafe inbound request id is replaced
- The 500 response leaks nothing
- **The 500 still carries the middleware headers and CORS** - a direct regression guard for the bug
  found in module 07
- Every `/tasks` route documents a 404 in the OpenAPI schema
- `TaskCreate` has no `status` property and `TaskReplace` does

That last pair means the "a client cannot open a task as already done" rule is enforced at the
schema level and asserted from the generated document, not just from a request that happens to fail.

## Why It Is Done This Way

**Why `TaskCreate`, `TaskReplace` and `TaskUpdate` are three classes.** Create must not accept
`status`, because every task starts as `todo`. Replace must accept it, because PUT replaces the
whole resource and the client has to be able to state the new status. Update must have every field
optional. One class cannot be all three.

**Why `store.py` is a class rather than module-level dicts.** Purely so `reset()` exists. That one
method is the difference between a suite that is order-independent and one that only passes in the
order it was written.

**Why the store method signatures look like a database repository.** Module 11 should replace the
body of each method rather than every call site.

**Why `_require()` exists.** Four handlers need the same 404. Extracting it means the message is
worded once, and `test_404_message_is_the_same_from_every_endpoint` asserts that clients see one
message rather than four near-identical ones.

**Why `complete` is its own endpoint and not `PATCH {"status": "done"}`.** It is a state transition
with a rule - completing an already-complete task is a 409. Expressing that through a generic field
edit would mean the rule lives in a conditional inside `PATCH`, applying to some values of one field
and not others.

**Why a duplicate title is a 409 on create.** Real task managers usually allow duplicate titles, so
this is arguably wrong for the domain. It is here so create has a conflict path to test, and saying
so is better than pretending it is a considered product decision.

**Why the parameter is `status_filter` with `alias="status"`.** `status` shadows the imported
`fastapi.status` module. The alias keeps the public API name correct despite a local naming problem.

**Why tests are grouped into classes.** `TestCreate`, `TestList`, `TestConflict` and so on give the
report structure and let `-k` select a group. No shared state lives on the classes; they are purely
namespaces.

## Known Gaps

- No coverage measurement. `pytest-cov` would show which branches the 91 tests never reach.
- No async tests. Every endpoint here is synchronous; `httpx.AsyncClient` and `pytest-asyncio` arrive
  with module 10.
- The store is not thread-safe and vanishes on restart. Module 11.
- No property-based or fuzz testing. The 422 cases are hand-picked examples.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8, pytest 9.1.1.

```
=== full suite ===
91 passed in 0.42s

=== order independence ===
normal order          91 passed in 0.42s
reversed order        91 passed in 0.43s
test_tasks_crud.py    32 passed
test_tasks_errors.py  29 passed
test_contract.py      30 passed

=== the isolation fixture is load-bearing ===
autouse disabled      9 failed, 82 passed
autouse restored      91 passed

=== the security fix ===
before: 1 failed - the 500 response contained postgres://user:pw@host/db
after : 91 passed - debug detail is the exception type only

06 debug 500 details: [{"message": "Unhandled ZeroDivisionError. The traceback is in the server log.",
                        "type": "ZeroDivisionError"}]
06 leaks 'division by zero': False
07 headers intact: True   07 reference matches header: True
```

## What I Learned

- A test caught a security bug that a careful read of my own writing did not. The module 06 README
  argued against including exception messages in responses, and the code included them anyway. The
  gap between what you believe you did and what you did is exactly the gap tests close.
- Verifying that a fixture is load-bearing is worth the two minutes. Disabling `autouse` and getting
  9 failures proved the isolation is real. A suite that passes because nothing depends on the setup
  is a suite that will pass after the setup silently breaks.
- `TestClient`'s two defaults both hide failures: no lifespan without `with`, and 500s re-raised
  rather than returned. Either one lets a suite look green while never exercising the code it was
  supposed to cover.
- `parametrize` is not a tidier loop. It produces separate test identities, so all five failures are
  visible at once instead of only the first.
- Contract tests catch a different class of regression than endpoint tests. The one asserting that a
  500 still carries CORS headers would have caught the module 07 bug immediately; no per-endpoint
  test would have noticed.
- Designing `store.py` as a class with `reset()` was a testing decision made in the production code.
  Testability is a property of the design, not something a test suite can add afterwards.
- Writing the failure path tests took longer than the happy path ones and found more. 29 of the 91
  tests are failure cases and they are the ones that broke during development.

## Screenshots

_To add: `pytest -v` output showing the grouped class names, and the original failing run of
`test_the_500_response_leaks_nothing`._

## Navigation

[Previous](../07-middleware-and-cors/) | [All modules](../README.md) | [Next](../09-dependency-injection/)
