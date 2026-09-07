# 11 - Database and Migrations

## What This Project Does

A persistent notes API. Users own notes, the schema is owned by Alembic rather than by
`create_all`, the session is a `yield` dependency, and the test suite runs the real migrations
against a throwaway database and leaves nothing behind.

**65 tests.** Building it surfaced three real bugs, one of which made the entire test suite pass for
the wrong reason. All three are written up below, because they are the most useful part of the
module.

This is the first module to use the package layout the guide specifies for 11 onward.

## Topics Covered

- SQLAlchemy 2.0 declarative style: `Mapped[]`, `mapped_column()`, `DeclarativeBase`
- Engine, `sessionmaker`, and why `expire_on_commit=False` matters for an API
- The session as a `yield` dependency - module 09's UnitOfWork made real
- Relationships, foreign keys, and cascade deletes
- `from_attributes` turning ORM objects into responses
- Alembic: init, autogenerate, upgrade, downgrade, and batch mode
- The N+1 query problem, counted and fixed with `selectinload`
- Transactional test isolation, and the SQLite quirk that silently breaks it
- SAVEPOINTs, and why a bare `rollback()` in a handler is usually wrong

## Project Layout

```
11-database/
|-- alembic.ini
|-- alembic/
|   |-- env.py                     URL from settings, batch mode, compare_type
|   |-- versions/
|       |-- ..._create_users_and_notes.py
|       |-- ..._add_archived_to_notes.py
|-- app/
|   |-- main.py                    app, lifespan, health
|   |-- config.py                  settings, absolute SQLite paths
|   |-- database.py                engine, SessionLocal, Base, SQLite fixes
|   |-- models.py                  User, Note
|   |-- schemas.py                 Pydantic in/out + error envelope
|   |-- dependencies.py            get_db, pagination, 404 resolvers
|   |-- routers/users.py notes.py
|   |-- errors.py handlers.py middleware.py context.py logging_config.py
|-- tests/
    |-- conftest.py                migrated test DB, transactional isolation, query counter
    |-- test_users.py              21 tests
    |-- test_notes.py              32 tests
    |-- test_migrations.py         12 tests
```

## How to Run

The schema does not exist until a migration creates it:

```bash
alembic upgrade head
```

```bash
uvicorn app.main:app --reload
```

```bash
pytest
```

Useful Alembic commands:

```bash
alembic current
```

```bash
alembic history --verbose
```

```bash
alembic revision --autogenerate -m "describe the change"
```

```bash
alembic downgrade -1
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/users` | Register a user |
| GET | `/users` | List users, paginated |
| GET | `/users/{id}` | One user plus a note count |
| DELETE | `/users/{id}` | Delete a user and cascade to their notes |
| POST | `/users/{id}/notes` | Create a note |
| GET | `/users/{id}/notes` | That user's notes, filtered and paginated |
| GET | `/notes` | All notes with authors - **deliberately N+1** |
| GET | `/notes/eager` | The same, eager loaded |
| GET | `/notes/{id}` | One note |
| PATCH | `/notes/{id}` | Update |
| DELETE | `/notes/{id}` | Delete |
| GET | `/health` | Health check that touches the database |

## Three Bugs Worth Reading About

### 1. The transactional test isolation did nothing

The test fixture opens a connection, begins a transaction, runs the test, and rolls back. Standard
recipe. Then tests began failing with `409 Conflict` because a user created in one test was still
there in the next.

Measured directly:

```
run1: status=201
run1: rows persisted after rollback = 1
run2: status=409
run2: rows persisted after rollback = 1
```

The row survived an explicit `rollback()`.

The cause is `pysqlite`, the standard library's SQLite driver. It manages transactions itself and
does not emit `BEGIN` where SQLAlchemy expects one, so `connection.begin()` never opened a real
transaction and the rollback had nothing to undo. The documented fix hands control back to
SQLAlchemy:

```python
@event.listens_for(target_engine, "connect")
def _on_connect(dbapi_connection, connection_record):
    dbapi_connection.isolation_level = None

@event.listens_for(target_engine, "begin")
def _on_begin(connection):
    connection.exec_driver_sql("BEGIN")
```

What makes this worth dwelling on is the failure mode. Without it, a suite that *looks* isolated is
not, every test silently depends on what ran before it, and the tests still pass right up until one
of them happens to collide. The suite was green in an earlier form for exactly that reason.

Confirmed load-bearing by removing it again:

```
without the transaction fix: 4 failed, 23 passed, 38 errors
restored                   : 65 passed
```

It also affects the application, not only the tests: `get_db`'s rollback-on-failure would have been
just as ineffective.

### 2. A caught IntegrityError destroyed unrelated work

`create_user` originally did the obvious thing:

```python
db.add(user)
try:
    db.flush()
except IntegrityError:
    db.rollback()
    raise ConflictError(...)
```

A test asserting that a rejected duplicate leaves the existing user alone failed, and it was right
to. `db.rollback()` discards the **entire** transaction, not the failed statement - so any work the
request had already done goes with it.

The fix is a SAVEPOINT:

```python
with db.begin_nested():
    db.add(user)
    db.flush()
```

Now only the failed insert is undone. This is the correct production behaviour, not a test
accommodation.

### 3. PATCH with an explicit null returned 500

`NoteUpdate` declares `title: str | None = None`, where `None` means "not supplied" and
`exclude_unset=True` tells that apart from a value. But the annotation also *accepts* an explicit
`null`, which was then assigned to a `NOT NULL` column - producing an `IntegrityError` and a 500
where a 422 belonged.

Fixed with a validator, which only runs when the client actually sent the field because Pydantic
does not validate defaults:

```python
@field_validator("title", "body", "archived")
@classmethod
def reject_explicit_null(cls, value, info):
    if value is None:
        raise ValueError(f"{info.field_name} cannot be null; omit it instead")
    return value
```

## How It Works

### Alembic owns the schema

`lifespan` deliberately does **not** call `Base.metadata.create_all()`. Doing so would build tables
from the models on first run, which then diverge from the migration history invisibly - and the
first deployment to a database that has actually been migrated fails in a way nobody can reproduce
locally.

`alembic/env.py` takes the URL from application settings rather than from `alembic.ini`, so the two
can never be pointed at different databases. `alembic.ini` therefore ships with an empty
`sqlalchemy.url`, which also keeps credentials out of version control.

The first migration was autogenerated from the models. Then `archived` was added to `Note` and a
second migration was autogenerated for it:

```
INFO  [alembic.autogenerate.compare.tables] Detected added column 'notes.archived'
```

Alembic refuses to autogenerate against a database that is not at head, which is correct and worth
knowing:

```
ERROR [alembic.util.messaging] Target database is not up to date.
```

SQLite cannot `ALTER` most things, so `render_as_batch` rebuilds the table instead - create new,
copy, drop old, rename. Visible in the generated migration:

```python
with op.batch_alter_table('notes', schema=None) as batch_op:
    batch_op.add_column(sa.Column('archived', sa.Boolean(), server_default=sa.text('0'), nullable=False))
```

Without it, any `ALTER COLUMN` migration fails on SQLite while working fine on PostgreSQL.

`server_default` on a `NOT NULL` column is not optional either: adding one without a default fails
against any table that already has rows.

### The migration drift test

The most valuable test in the module, and the one most projects do not have:

```python
diff = compare_metadata(context, Base.metadata)
assert diff == [], f"models and migrations have diverged: {diff}"
```

`compare_metadata` is what `alembic revision --autogenerate` runs to decide what to write. An empty
diff means running autogenerate now would produce nothing, which is the definition of being in sync.

Verified by editing a model without writing a migration:

```
model changed, no migration written -> 1 failed
    assert diff == [], f"models and migrations have diverged: {diff}"
model restored                      -> 1 passed
```

Without it, forgetting a migration is invisible until a deployment builds the schema from migrations
alone and a column the code needs is not there.

There are also tests for a single unbranched head, a full `upgrade -> downgrade to base -> upgrade`
round trip, and a one-step downgrade removing only `archived`. A downgrade nobody runs is a
downgrade that does not work, and the moment it is needed is the worst moment to find out.

### The session dependency

Module 09's `UnitOfWork`, now real:

```python
def get_db():
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    else:
        session.commit()
    finally:
        session.close()
```

Each request gets its own session and its own connection. A module-level session shared between
requests would interleave two users' work into one transaction, which is data corruption rather than
untidiness. Committing here means no handler can forget, and module 09 already measured that this
rollback fires for a deliberately raised 404 as well as an unexpected exception - tested again here
against a real database.

`session.close()` returns the connection to the pool. Omitting it exhausts the pool after
`pool_size + max_overflow` requests, and the symptom is the application hanging rather than erroring.

`expire_on_commit=False` on the sessionmaker matters for an API specifically. With the default,
every attribute of a committed object is invalidated, so the response model reading `note.id` after
the dependency commits fires a fresh SELECT - and against a closed session, raises
`DetachedInstanceError` instead.

### N+1, counted

`GET /notes` fetches notes and lets the response model read `note.author` on each one. Every read is
a separate lazy SELECT. `GET /notes/eager` adds `selectinload(Note.author)`.

Worst case, 30 notes with 30 distinct authors:

```
page size  5  ->  lazy   6 SELECTs   eager 2 SELECTs
page size 10  ->  lazy  11 SELECTs   eager 2 SELECTs
page size 20  ->  lazy  21 SELECTs   eager 2 SELECTs
page size 30  ->  lazy  31 SELECTs   eager 2 SELECTs
```

Exactly N+1 against 2, flat.

With repeated authors it is less dramatic, because the session's identity map spares a second lookup
for an author already loaded:

```
30 notes, 6 distinct authors:  lazy 7 SELECTs   eager 2 SELECTs
```

So the lazy version scales with the number of *distinct parents*, not rows. That is still unbounded,
and it is worse in production than in a test because a bigger dataset means more distinct parents.

`selectinload` issues one extra `WHERE id IN (...)`. `joinedload` is the alternative - one query with
a JOIN - and is usually worse for a collection because the JOIN duplicates the parent row once per
child.

Both endpoints return byte-identical data, which a test asserts. The only difference is the query
count, which is why counting is the only way to catch this.

### Test isolation

```python
connection = test_engine.connect()
transaction = connection.begin()
sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
```

`join_transaction_mode="create_savepoint"` is what makes this work. A session bound to a connection
that already has a transaction would otherwise join it, and the first `commit()` inside a request
would end the outer transaction - leaving the rollback with nothing to undo. With `create_savepoint`
each session opens a SAVEPOINT, so `commit()` behaves normally from the application's point of view
while the outer rollback still discards everything.

The override creates a **fresh session per request**, mirroring `get_db`, rather than sharing one
session with the test. Sharing one initially made two tests pass for the wrong reason and two fail
for the wrong reason: a deleted row stayed visible through the identity map, and one request's
rollback undid an earlier request's work. Neither would happen in production, where every request
has its own session.

## Why It Is Done This Way

**Why models and schemas are separate files and separate classes.** An ORM model describes storage;
a schema describes the wire. Merging them makes a column rename an API breaking change and exposes
every internal column by default.

**Why uniqueness is a database constraint and not a query.** Checking for an existing row and then
inserting is a race: two concurrent requests both see nothing and both insert. Catching
`IntegrityError` is the only version that is actually correct.

**Why `flush()` and not `commit()` in the handler.** `flush` sends the INSERT without ending the
transaction, so a constraint violation surfaces where it can become a 409. Left to the dependency's
commit, it would arrive as an unhandled 500 after the handler has returned.

**Why relative SQLite paths are made absolute.** `sqlite:///./app.db` resolves against the working
directory, so `uvicorn` from one place and `alembic` from another would create two different files
and neither would obviously be wrong. Anchoring to the module directory means every entry point
agrees.

**Why `PRAGMA foreign_keys=ON`.** SQLite does not enforce foreign keys unless asked, per connection.
Without it a cascade delete silently does nothing and orphans accumulate - and the same code against
PostgreSQL behaves differently, which is the worst kind of difference.

**Why `note_count` is a COUNT query rather than `len(user.notes)`.** The latter loads every note row
into memory to discard all but the number.

**Why the tests assert against the database as well as the response.** A handler could build a
plausible response without persisting anything, and an endpoint-only test would not notice.

## Known Gaps

- SQLite only. PostgreSQL is module 16, and the differences that matter are already handled:
  `render_as_batch`, the foreign key pragma, and the transaction fix all become no-ops.
- Synchronous SQLAlchemy with `def` endpoints. That is the *correct* pairing given module 10 - a
  sync driver inside `async def` would block the event loop. Async SQLAlchemy plus `asyncpg` is the
  alternative, and it is a larger change than it looks because every query site changes too.
- No ownership checks. Anyone can read or delete anyone's notes. Module 12.
- No connection pool metrics or slow query logging.
- Running the tests creates an empty `app.db`. The lifespan's startup probe connects to the real
  engine, which is not overridable because lifespan has no request to hang a dependency on, and
  SQLite creates the file on connect. Harmless and gitignored, but untidy - the alternatives are to
  drop the startup probe, or to make the engine itself swappable, and neither is clearly better than
  a stray empty file.
- Timestamps are set in Python via `default=utcnow`, not by the database. Fine for one process,
  worth revisiting with several.

## Verification

Run against Python 3.12.0, SQLAlchemy 2.0.51, Alembic 1.18.5.

```
=== test suite ===
65 passed in 1.04s
reversed order          65 passed
test_users.py           21 passed
test_notes.py           32 passed
test_migrations.py      12 passed

=== the SQLite transaction fix is load-bearing ===
without it   4 failed, 23 passed, 38 errors
restored     65 passed

=== the drift test catches drift ===
model changed, no migration written  ->  1 failed
model restored                       ->  1 passed

=== N+1, worst case (30 notes, 30 authors) ===
page size  5  lazy  6   eager 2
page size 10  lazy 11   eager 2
page size 20  lazy 21   eager 2
page size 30  lazy 31   eager 2

=== migrations ===
alembic upgrade head
  -> 5e673790df7f, create users and notes
  -> cf34432da220, add archived to notes
alembic current  ->  cf34432da220 (head)
autogenerate against a stale DB  ->  "Target database is not up to date"

=== live server, real SQLite file ===
GET  /health          {"status":"ok","version":"0.2.0","database":"reachable"}
POST /users           201  {"id":1,"username":"ada",...}
POST /users/1/notes   201  {"id":1,"title":"Persisted note","archived":false,...}
GET  /users/1         200  {...,"note_count":1}
POST /users (dup)     409  {"error":{"code":"conflict",...}}
```

## What I Learned

- A transactional test fixture can look correct and isolate nothing. `pysqlite` does not begin
  transactions the way SQLAlchemy expects, so the rollback discarded nothing and every test leaked
  into the next. The suite was green while being completely non-isolated, which is worse than a
  failing suite.
- `db.rollback()` inside a handler is almost always too big a hammer. It discards the whole
  transaction, including work that succeeded. `begin_nested()` scopes the undo to the statement that
  actually failed.
- `create_all` in application startup is a trap even though it is what most tutorials show. It makes
  the models and the migration history diverge silently.
- The migration drift test is worth more than several endpoint tests. Forgetting a migration is
  invisible locally and fatal on deploy, and one `compare_metadata` call catches it every run.
- Alembic refusing to autogenerate against a database that is not at head is a feature. It stops a
  new migration being diffed against a stale schema and containing the previous migration's changes
  as well.
- An optional field in a PATCH schema accepts an explicit `null` as well as absence, and the two
  need different handling. Pydantic not validating defaults is what makes the validator fix work.
- `expire_on_commit=False` is close to mandatory for an API. The default invalidates every attribute
  at commit, and the response model reads them afterwards.
- Counting queries is the only way to see an N+1. It is invisible in the code, invisible in the
  response, and only shows up in timings once the dataset is large enough to hurt.
- The identity map makes N+1 look milder than it is in a small test. 30 notes with 6 authors cost 7
  queries; with 30 authors, 31.

## Navigation

[Previous](../10-async-and-concurrency/) | [All modules](../README.md) | [Next](../12-authentication/)
