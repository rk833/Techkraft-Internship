# 04 - Request Body and Response Models

## What This Project Does

A user registration API. Clients send a password; the API never returns one. That single
requirement is what the whole module is built around, because meeting it properly means the request
schema and the response schema have to be two different classes rather than one class with a filter
bolted on.

It also closes the gap left open in module 02, where `POST /books` took an untyped `dict` and
cheerfully stored `"year": "banana"`.

## Topics Covered

- Accepting a JSON request body as a Pydantic model
- `response_model`, and why the output schema differs from the input schema
- `status_code` on route decorators
- 201 Created and 204 No Content
- `response_model_exclude_none`
- `model_dump(exclude_unset=True)` for PATCH
- Multiple `Body()` parameters, and `Body(embed=True)` for a single one
- Documenting non-200 responses with `responses=`

## Project Layout

```
04-request-body-and-response-models/
|-- main.py                  app creation and router registration
|-- schemas.py               UserBase, UserCreate, UserRead, UserUpdate, Message
|-- data.py                  in-memory store, records carry password + internal_note
|-- routers/
    |-- __init__.py
    |-- users.py             8 routes
```

## How to Run

Activate the shared `.venv` from the repository root, then from inside this folder:

```bash
uvicorn main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

Swagger now shows a real request body schema with an example, which module 02's `dict` endpoint
could not produce.

## Endpoints

| Method | Path | Body | Returns | Success |
|--------|------|------|---------|---------|
| POST | `/users` | `UserCreate` | `UserRead` | 201 |
| GET | `/users` | | `list[UserRead]` | 200 |
| GET | `/users/{user_id}` | | `UserRead` | 200 |
| GET | `/users/{user_id}/profile` | | `UserRead`, nulls omitted | 200 |
| PATCH | `/users/{user_id}` | `UserUpdate` | `UserRead` | 200 |
| POST | `/users/{user_id}/change-password` | two `Body()` scalars | `Message` | 200 |
| POST | `/users/{user_id}/deactivate` | `Body(embed=True)` | `UserRead` | 200 |
| DELETE | `/users/{user_id}` | | nothing | 204 |
| GET | `/health` | | status | 200 |

## How It Works

### Two schemas, not one

```python
class UserBase(BaseModel):        # username, email, full_name, bio
class UserCreate(UserBase):       # + password
class UserRead(UserBase):         # + id, is_active, created_at
```

`UserRead` has no `password` attribute. This is stronger than filtering, because there is no flag to
misconfigure and no exclusion list to forget to update. FastAPI cannot serialise a field the class
does not declare.

The handlers deliberately do the wrong-looking thing to prove it. Every one returns the raw stored
dict, which contains both a `password` and an `internal_note`:

```
stored record keys  : ['bio','created_at','email','full_name','id','internal_note','is_active','password','username']
response keys       : ['bio','created_at','email','full_name','id','is_active','username']
password in response: False
internal_note in it : False
```

And across the whole collection endpoint - `response_model` applies elementwise to a list, not just
to the outer container:

```
GET /users -> 4 users, any password field: False
```

The generated schema agrees, which means Swagger tells clients the truth:

```
UserRead   : ['bio','created_at','email','full_name','id','is_active','username']
UserCreate : ['bio','email','full_name','password','username']
```

### The body is validated before the handler runs

Same principle as module 03's query parameters, now applied to JSON:

```
422  password too short   password: String should have at least 8 characters
422  username too short   username: String should have at least 3 characters
422  malformed email      email: value is not a valid email address: An email address must have an @-sign.
422  missing fields       email: Field required; password: Field required
```

`EmailStr` does the email check. It needs the separate `email-validator` package, which `pydantic`
does not pull in by itself - it is in the root `requirements.txt` for that reason.

### PATCH and exclude_unset

```python
changes = payload.model_dump(exclude_unset=True)
user.update(changes)
```

`exclude_unset=True` is the load-bearing part. Without it the dump contains every field the model
declares, with `None` for anything the client omitted, so a PATCH of `{"bio": "hello"}` would wipe
`full_name` and `email`.

Proven:

```
before: {"username":"rkhadka","full_name":"Ridesha Khadka","bio":"Learning FastAPI."}
PATCH  /users/1  {"bio":"Updated bio."}  -> 200
after : {"username":"rkhadka","full_name":"Ridesha Khadka","bio":"Updated bio."}
full_name survived: True
```

It also distinguishes "the client omitted this field" from "the client explicitly sent `null`",
which a plain optional-with-a-default cannot express. That distinction matters the moment a client
wants to clear a field deliberately.

### response_model_exclude_none

Two endpoints, the same response model, one flag apart:

```
/users/2          keys: ['bio','created_at','email','full_name','id','is_active','username']
/users/2/profile  keys: ['created_at','email','id','is_active','username']
dropped by exclude_none: ['bio','full_name']
```

Useful when a consumer treats a missing key differently from a null, or when payload size matters.
Not a default, because a stable key set is usually easier for a client to consume.

### Body() with more than one parameter

```python
current_password: Annotated[str, Body(min_length=8)],
new_password: Annotated[str, Body(min_length=8)],
```

A single body parameter *is* the whole request body. With two or more, FastAPI switches behaviour
and nests them under their parameter names, so the payload becomes
`{"current_password": "...", "new_password": "..."}`.

`Body(embed=True)` forces that same nesting for a single parameter, which is what `deactivate` uses
so its body is `{"reason": "..."}` rather than a bare JSON string.

```
200  change-password  correct current    {"detail":"Password updated"}
403  change-password  wrong current      {"detail":"Current password is incorrect"}
422  change-password  same as current    {"detail":"New password must differ"}
422  change-password  missing one param  new_password: Field required
200  deactivate       {"reason":"user requested"}
422  deactivate       {"reason":"x"}     reason: String should have at least 3 characters
```

### Status codes and the empty 204

```
204  DELETE /users/3    content-length: None    body repr: ''
```

Genuinely empty, not `null`. `DELETE` declares no `response_model`, because 204 means there is no
body to model.

## Why It Is Done This Way

**Why `UserBase` exists.** Username and email rules live in one place. Split across `UserCreate` and
`UserRead`, a change to `max_length` could be applied to one and forgotten on the other, and the two
would drift without any error.

**Why `UserUpdate` does not inherit from `UserBase`.** `UserBase` makes username and email required,
and a PATCH body of `{"bio": "..."}` has to be valid. The optionality has to be redeclared. It is
repetitive and it is the standard approach - the alternatives (a generic `Partial[T]` helper) cost
more clarity than they save.

**Why `response_model=` rather than a `-> UserRead` return annotation.** FastAPI accepts either.
These handlers return plain dicts, not `UserRead` instances, so a `-> UserRead` annotation would be
a lie to any type checker even though FastAPI would handle it. `response_model=` states the contract
without misdescribing the function. Once module 11 returns real ORM objects, the return annotation
becomes the better choice.

**Why `responses={404: {"model": Message}}` on the get-one route.** Without it the schema claims the
endpoint only ever returns a `UserRead`. That is a documented lie, and clients generated from the
schema would have no type for the error case.

**Why 409 for a duplicate username rather than 422.** The request was well-formed and the values
were individually valid; the conflict is with existing state. 422 would be misleading, and it would
collide with the automatic validation errors a client already handles.

**Why the password is stored in plain text.** It is wrong, and it is labelled as wrong in `data.py`.
Hashing is module 12. Storing it visibly here also gives the response model something real to hide,
which makes the demonstration honest rather than staged.

## Known Gaps

- **Extra fields in the request body are silently ignored.** `{"username":"zed", ..., "is_admin":true}`
  returned 201 and the `is_admin` key was dropped. Nothing is exploitable here, because the handler
  builds the record from `payload.model_dump()` and `is_admin` never enters it. But silently
  discarding input a client thought was meaningful is poor behaviour, and it becomes a real mass
  assignment risk in any handler that does `user.update(payload)`. The fix is
  `model_config = ConfigDict(extra="forbid")`, which is module 05.
- **Error bodies are still inconsistent** - automatic 422s return a structured list under `detail`,
  hand-raised ones return a string. Carried over from module 03; module 06 fixes it.

## Verification

Run against Python 3.12.0, FastAPI 0.140.8, Pydantic 2.13.4.

```
=== password never leaves ===
201  POST /users                  {"username":"italo",...,"id":3,"is_active":true,"created_at":"..."}
     stored keys  : [...,'internal_note','is_active','password','username']
     response keys: ['bio','created_at','email','full_name','id','is_active','username']
     password in response: False        internal_note in response: False
200  GET  /users  -> 4 users, any password field: False

=== request validation ===
422  password too short    password: String should have at least 8 characters
422  username too short    username: String should have at least 3 characters
422  malformed email       email: value is not a valid email address
422  missing fields        email: Field required; password: Field required
201  extra junk ignored    is_admin silently dropped (see Known Gaps)
409  duplicate username    {"detail":"That username is taken"}

=== read ===
200  GET /users/1          full record, filtered
404  GET /users/999        {"detail":"No user with id 999"}
422  GET /users/0          user_id: Input should be greater than or equal to 1

=== exclude_none ===
/users/2         keys: ['bio','created_at','email','full_name','id','is_active','username']
/users/2/profile keys: ['created_at','email','id','is_active','username']

=== PATCH exclude_unset ===
PATCH /users/1 {"bio":"Updated bio."} -> full_name survived: True

=== Body() ===
200  change-password correct       {"detail":"Password updated"}
403  change-password wrong current {"detail":"Current password is incorrect"}
422  change-password same as old   {"detail":"New password must differ"}
422  change-password missing param new_password: Field required
200  deactivate {"reason":"user requested"}
422  deactivate {"reason":"x"}     reason: String should have at least 3 characters

=== 204 ===
204  DELETE /users/3   content-length: None   body: ''
404  DELETE /users/3   {"detail":"No user with id 3"}

=== declared response schemas ===
GET    /users                            {'200': 'UserRead'}
POST   /users                            {'201': 'UserRead', '422': 'HTTPValidationError'}
GET    /users/{user_id}                  {'200': 'UserRead', '404': 'Message', '422': 'HTTPValidationError'}
GET    /users/{user_id}/profile          {'200': 'UserRead', '422': 'HTTPValidationError'}
PATCH  /users/{user_id}                  {'200': 'UserRead', '422': 'HTTPValidationError'}
POST   /users/{user_id}/change-password  {'200': 'Message',  '422': 'HTTPValidationError'}
POST   /users/{user_id}/deactivate       {'200': 'UserRead', '422': 'HTTPValidationError'}
DELETE /users/{user_id}                  {'204': 'no body',  '422': 'HTTPValidationError'}
```

## What I Learned

- Omitting a field from the response class is a much stronger guarantee than excluding it. A filter
  can be misconfigured; a missing attribute cannot be serialised. Returning the raw record with the
  password still in it and watching it not appear is the demonstration that makes this stick.
- `exclude_unset` is the difference between a working PATCH and one that silently destroys data. It
  is a single keyword argument and it is easy to leave out, and the bug it causes does not raise -
  it just quietly nulls fields.
- `Body()` changes meaning based on how many of them there are. One is the entire body; two or more
  get nested under their names. `embed=True` exists solely to get the second behaviour with one
  parameter, and without knowing that the API design gets contorted to avoid it.
- `EmailStr` needs `email-validator` installed separately. `pydantic` does not depend on it, and the
  error only appears at import time when a model using it is defined.
- Pydantic ignores unknown fields by default. Sending `"is_admin": true` returned 201 with no
  complaint. That default is a mass assignment hazard in any handler that spreads the payload
  straight into a record.

## Navigation

[Previous](../03-path-and-query-parameters/) | [All modules](../README.md) | [Next](../05-pydantic-and-settings/)
