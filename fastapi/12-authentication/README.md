# 12 - Authentication and Authorisation

## What This Project Does

Puts real identity on module 11's notes API. Passwords are bcrypt hashed, sessions are JWTs,
notes belong to whoever created them, and administrators are a role rather than a shared key.

**121 tests.** The security claims are not asserted, they are demonstrated: every control was
deliberately removed and the suite re-run to prove it was load-bearing rather than decorative.

## Topics Covered

- bcrypt: salts, cost factors, and the 72-byte limit
- Why plain text, MD5 and SHA-256 are all unacceptable for passwords
- JWT structure: header, payload, signature, and what is and is not secret
- Access tokens and refresh tokens, and why the distinction is enforced
- `OAuth2PasswordBearer` and the Swagger Authorize button
- A `get_current_user` dependency that checks more than the signature
- Role-based access control
- Authentication (401) versus authorisation (403)
- Username enumeration by timing, and the defence
- A migration that adds a required column to a populated table

## Project Layout

```
12-authentication/
|-- alembic/versions/
|   |-- ..._create_users_and_notes.py
|   |-- ..._add_archived_to_notes.py
|   |-- ..._add_auth_columns_to_users.py    hand-adjusted, three-step
|-- app/
|   |-- security.py            hashing and tokens, no FastAPI imports
|   |-- dependencies.py        get_current_user, require_admin, get_own_note
|   |-- routers/auth.py        register, login, refresh, me, change-password
|   |-- routers/notes.py       scoped to the token holder
|   |-- routers/admin.py       role-guarded at the router
|   |-- models.py schemas.py config.py database.py errors.py handlers.py ...
|-- tests/
    |-- test_security.py       35 tests, the primitives, no HTTP
    |-- test_auth.py           54 tests, registration/login/refresh/boundary
    |-- test_authorization.py  32 tests, ownership and roles
```

## How to Run

```bash
alembic upgrade head
```

```bash
uvicorn app.main:app --reload
```

```bash
pytest
```

`JWT_SECRET_KEY` must be set in the shared root `.env`. The service refuses to start without one -
there is deliberately no default, because a signing secret with a fallback ships to production
unchanged and anyone who has read the source can mint admin tokens.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

In Swagger UI, click **Authorize**, enter a username and password, and every protected endpoint is
then callable from the page.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | none | Create an account |
| POST | `/auth/login` | none | Form-encoded, returns a token pair |
| POST | `/auth/refresh` | refresh token | New token pair |
| GET | `/auth/me` | access token | The caller's own account |
| POST | `/auth/change-password` | access token | Requires the current password |
| POST/GET | `/notes` | access token | Create / list your own |
| GET/PATCH/DELETE | `/notes/{id}` | access token | Only your own |
| GET | `/admin/users`, `/admin/stats` | admin | |
| PATCH | `/admin/users/{id}/role` | admin | Promote or demote |
| POST | `/admin/users/{id}/deactivate` `/activate` | admin | |
| DELETE | `/admin/users/{id}` | admin | Cascades to notes |

## Every Control, Proven Load-Bearing

Each line below is the full suite re-run with one security control deleted:

```
remove the algorithms= whitelist       30 failed, 81 passed, 10 errors
remove the token type check             4 failed, 117 passed
remove the note ownership check         5 failed, 116 passed
remove the admin role check             4 failed, 117 passed
stop checking is_active                 2 failed, 119 passed
all restored                          121 passed
```

A security test that passes whether or not the control exists is worse than no test, because it
reads as assurance. These do not.

## How It Works

### Passwords

```python
bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
```

bcrypt generates and embeds a fresh random salt, so the same password hashed twice produces two
different strings - which is what defeats rainbow tables, and why there is no separate salt column.
Tested directly, including that two users choosing the same password get different hashes, so
cracking one does not crack the other.

The cost factor lives inside the hash, so raising it later does not invalidate existing hashes.
`needs_rehash()` plus a rehash on successful login upgrades them transparently, at the one moment
the plain password is available.

Measured cost:

```
one hash at cost 12: 189ms
one hash at cost  4:   5ms   (used by the test suite)
```

That 189ms is the point of bcrypt - it is deliberately expensive, so offline brute force is slow.
It is also why **every handler in `auth.py` is a plain `def`**. Module 10 measured what 200ms of
CPU work inside an `async def` does to an event loop; a `def` endpoint runs in the threadpool and
blocks a worker thread instead of the whole server.

bcrypt 5 **raises** above 72 bytes rather than truncating:

```
ValueError: password cannot be longer than 72 bytes
```

So the schema caps the field at 72 and a long password is a 422 naming the field, not a 500. Silent
truncation would be worse than either: two passwords sharing a 72-byte prefix would become the same
password.

### The timing defence

`verify_password` runs a bcrypt check against a dummy hash even when the user does not exist:

```
cost factor 12, median over 12 runs
  wrong password, user exists  :  181.6ms
  unknown username             :  179.5ms
  ratio                        :  1.01x
```

Without it, an unknown username returns in about 0.00ms while a wrong password costs 180ms. That
difference is an account-enumeration oracle usable by anyone, with no valid credentials at all.
Both paths also return the byte-identical error message, which a test asserts.

### Tokens

A JWT is three base64url segments: header, payload, signature. The first two are **encoded, not
encrypted** - two tests make this concrete:

- `test_the_payload_is_readable_without_the_key` decodes the claims with `verify_signature=False`
  and reads the role.
- `test_but_it_cannot_be_altered` edits that role to `admin`, re-signs with the wrong key, and
  confirms it is rejected.

So a token may carry an id and a role, and must never carry anything secret.

`algorithms=[...]` is passed explicitly, and that is not stylistic. A decoder that trusts the
token's own header can be handed `alg=none` and asked to accept an unsigned token. There is a test
that mints exactly that token. Removing the whitelist breaks 30 tests.

Access and refresh tokens are both validly signed by this service, so the `type` claim is checked in
both directions:

- A refresh token cannot authorise a normal request - otherwise every session silently lasts the
  7-day refresh lifetime rather than 30 minutes.
- An access token cannot be exchanged at `/auth/refresh`.

### get_current_user checks four things

```python
1. a token was supplied
2. it verifies, has not expired, and is an access token
3. the user it names still exists
4. that user is still active
```

Steps 3 and 4 are the ones usually skipped. A token is a claim made minutes ago, and accounts get
deleted, disabled and demoted. Tested:

- a token for a deleted user is 401
- a token for a disabled user is 403
- deactivating an account locks it out on the **next request**, not when its token expires

`require_admin` re-reads the role from the database row for the same reason, so a demotion takes
effect immediately. A test demotes an admin mid-session and confirms the next request is 403.

### 401 versus 403

| | |
|---|---|
| **401** | "I do not know who you are." No token, expired token, forged token. |
| **403** | "I know exactly who you are, and the answer is still no." Valid token, insufficient role. |

Returning 401 for a permission failure tells the client to log in again, which cannot help and
produces a re-authentication loop. Both are tested against every admin route.

### Ownership, and why it is a 404

```python
if note.author_id != current_user.id and current_user.role != Role.ADMIN:
    raise NotFoundError(f"No note with id {note_id}")
```

Someone else's note returns **404, not 403**. A 403 would confirm the id exists, letting an
authenticated user enumerate the id space and learn how many notes the system holds. A test asserts
that "not yours" and "does not exist" are indistinguishable from outside.

Three further properties are tested:

- The list endpoint filters in the `WHERE` clause, not afterwards. Filtering after the query would
  leak through pagination - a page of 20 returning 3 rows tells you 17 belonged to someone else.
- `total` is scoped too, or it would disclose other people's note counts.
- `NoteCreate` has no `author_id` field, so a client cannot attribute a note to someone else. The
  owner comes from the token. Module 11's `/users/{user_id}/notes` was an authorisation hole waiting
  for authentication to exist.

### The migration that would have failed in production

Autogenerate produced a single ALTER adding `hashed_password` as NOT NULL with no default. Against
an empty database that works. Against a populated one it was measured failing:

```
sqlite3.IntegrityError: NOT NULL constraint failed: _alembic_tmp_users.hashed_password
```

Adding a required column to a table with rows is always three steps: add it nullable, backfill,
then apply the constraint. Doing it in one is a migration that passes locally and takes production
down.

The backfill value matters as much as the shape. Legacy rows get `"!"` - a string no bcrypt hash can
equal, since a real one begins with `$2b$` - so every legacy account is locked out until it resets.
Backfilling a real hash of a known value would give every legacy account the same working password.

Verified against a populated table:

```
legacy row after migration: ('legacy', '!', 'user', 1)
hashed_password notnull: True
```

Alembic's autogenerated `# please adjust!` comment is asking for exactly this.

## Live Run

```
POST /auth/register    201  {"id":1,"username":"alice","role":"user","is_active":true,...}
POST /auth/login       200  access token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
GET  /notes            401  (no token)
GET  /notes            200  (with token)
POST /notes            201  {"id":1,"title":"My private note","author_id":1,...}
GET  /admin/stats      403  {"error":{"code":"forbidden","message":"Administrator access is required"}}

login, wrong password  {"code":"unauthenticated","message":"Incorrect username or password"}
login, unknown user    {"code":"unauthenticated","message":"Incorrect username or password"}
                       identical, by design

stored in the database: alice  $2b$12$shDwKJAZzu0uVXjbsJNevujim...  user
```

## Why It Is Done This Way

**Why bcrypt and not SHA-256.** SHA-256 is designed to be fast, which is precisely wrong for
passwords - a GPU computes billions per second. bcrypt is deliberately slow and its cost is tunable
upward as hardware improves. MD5 and plain SHA are also unsalted by default, so identical passwords
produce identical hashes.

**Why `security.py` imports nothing from FastAPI.** These are primitives. Which status code a
failure maps to is an HTTP concern and lives in `dependencies.py`, so the hashing and token code is
testable without a request and reusable outside a web context.

**Why there is no endpoint that grants the admin role to a new account.** The first admin is created
out of band - in the test fixture, directly in the database. Any self-service route to `admin` is a
privilege escalation waiting to be found.

**Why an admin cannot demote, deactivate or delete themselves.** Without those checks the last
remaining admin can lock every administrator out with one request, recoverable only by editing the
database by hand.

**Why the current password is required to change a password.** A stolen access token should not be
enough to take permanent ownership of an account.

**Why the 409 on registration does not name the field.** "That email is taken" is a free
account-existence oracle.

**Why the 401 does not say why the token failed.** "Expired" versus "signature invalid" is useful
to us in the log and useful to an attacker in the response.

**Why the test suite uses `bcrypt_rounds=4`.** At the production cost of 12, the roughly sixty
hashes these tests perform would add about twelve seconds. Injected by overriding `get_settings`
rather than mutating the real settings.

## Known Gaps

- **No token revocation.** A stolen access token is valid until it expires, and logging out is
  purely client-side. Every token carries a `jti` so a denylist has something to key on, but there
  is no denylist. Real revocation needs server-side state - Redis, or a token version column bumped
  on password change.
- **Refresh tokens are not rotated or single-use.** A leaked refresh token is usable for seven days.
  Rotation plus reuse detection is the standard fix.
- **No rate limiting on login.** Nothing here slows down credential stuffing. bcrypt's cost is a
  partial defence, and `slowapi` arrives in module 17.
- **No account lockout or MFA.**
- **Tokens are returned in the response body**, so a browser client stores them in JavaScript-
  reachable storage and is exposed to XSS. `httpOnly` cookies plus CSRF protection is the
  alternative, with its own trade-offs.
- **No password strength rules** beyond a length minimum, and no check against known-breached
  password lists.
- **No audit log.** Admins can read any note, which moderation needs, and nothing records that they
  did.

## Verification

Run against Python 3.12.0, bcrypt 5.0.0, PyJWT 2.13.0.

```
=== suite ===
121 passed in 1.53s
reversed order           121 passed
test_security.py          35 passed
test_auth.py              54 passed
test_authorization.py     32 passed

=== every control is load-bearing ===
remove the algorithms= whitelist    30 failed, 81 passed, 10 errors
remove the token type check          4 failed, 117 passed
remove the note ownership check      5 failed, 116 passed
remove the admin role check          4 failed, 117 passed
stop checking is_active              2 failed, 119 passed
all restored                       121 passed

=== timing defence, cost factor 12 ===
wrong password, user exists   181.6ms
unknown username              179.5ms
ratio                           1.01x

=== bcrypt cost ===
cost 12: 189ms per hash        cost 4: 5ms per hash
>72 bytes: ValueError, not silent truncation

=== the migration against existing rows ===
naive single-ALTER version:  IntegrityError: NOT NULL constraint failed
three-step version:          ('legacy', '!', 'user', 1), notnull=True
```

## What I Learned

- Deleting a control and re-running the suite is the only way to know a security test is real. All
  five deletions broke tests; had any of them not, that control would have been untested despite
  looking covered.
- `algorithms=` in `jwt.decode` is not a formality. Removing it broke 30 tests, and in a real
  service it means an attacker can present an unsigned token claiming to be anyone.
- A valid signature is the smallest part of trusting a token. Whether the user still exists, is
  still active, and still holds the role are all things that can change within a token's lifetime,
  and none of them are in the token.
- Returning 404 instead of 403 for someone else's resource is a deliberate choice with a real
  reason. 403 confirms existence and hands over an enumeration oracle.
- The timing difference between "no such user" and "wrong password" is a genuine vulnerability, and
  the fix - hashing against a dummy value - is three lines. Measured at 181.6ms versus 179.5ms.
- bcrypt raising above 72 bytes rather than truncating is a good design, and it means the schema
  limit is required rather than tidy.
- Adding a required column to a populated table is three migration steps, and the naive version
  fails only when there is data - so it passes in every empty development database.
- The value used to backfill a password column is a security decision. `"!"` locks legacy accounts
  out; a real hash of a known string would silently give them all the same password.
- Putting the guard on the router rather than each endpoint means a route added later is protected
  by default. That default is the whole argument.

## Navigation

[Previous](../11-database/) | [All modules](../README.md) | [Next](../13-file-upload/)
