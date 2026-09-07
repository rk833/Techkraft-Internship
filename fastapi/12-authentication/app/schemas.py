"""Pydantic schemas.

Separate from models.py on purpose. An ORM model describes storage; a schema
describes the wire. Merging them means a column rename becomes an API breaking
change, and every internal column is exposed by default.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.errors import ErrorCode


class ErrorDetail(BaseModel):
    """One specific thing that was wrong."""

    field: str | None = None
    message: str
    type: str | None = None


class ErrorBody(BaseModel):
    """The contents of the error envelope."""

    code: ErrorCode
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    reference: str


class ErrorResponse(BaseModel):
    """Every failure from this API looks like this."""

    error: ErrorBody


class UserCreate(BaseModel):
    """Registration payload."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=80)


class UserRead(BaseModel):
    """A user as returned to the client.

    There is no hashed_password field and no password field. As in module 04,
    the guarantee comes from the attribute not existing rather than from a
    filter that could be misconfigured.
    """

    # from_attributes is what lets FastAPI build this straight from a User ORM
    # object. Module 05 practised it against a dataclass for exactly this.
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class UserWithCount(UserRead):
    """A user plus how many notes they have."""

    note_count: int


class NoteCreate(BaseModel):
    """A new note."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=120)
    body: str = Field(default="", max_length=10_000)


class NoteUpdate(BaseModel):
    """A partial update.

    The None defaults mean "not supplied", and model_dump(exclude_unset=True)
    tells that apart from an explicitly sent null. But an explicit null is
    still accepted by the annotation and would then be assigned to a NOT NULL
    column, so it has to be rejected here.

    A test found this: PATCH {"title": null} produced a 500 from an
    IntegrityError rather than a 422. Validators do not run on defaults, so
    these only fire when the client actually sent the field.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=120)
    body: str | None = Field(default=None, max_length=10_000)
    archived: bool | None = None

    @field_validator("title", "body", "archived")
    @classmethod
    def reject_explicit_null(cls, value, info):
        """None is how absence is expressed, not a value a client may send."""
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null; omit it instead")
        return value


class NoteRead(BaseModel):
    """A note as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    archived: bool
    author_id: int
    created_at: datetime
    updated_at: datetime


class NoteWithAuthor(NoteRead):
    """A note with its author embedded.

    Reading `note.author` triggers a lazy load per note unless the query eager
    loaded it. That is the N+1 problem, and this schema is what makes it happen.
    """

    author: UserRead


class Page(BaseModel):
    """Pagination envelope, consistent with modules 03 and 09."""

    total: int
    count: int
    limit: int
    offset: int


class NotePage(Page):
    """A page of notes."""

    items: list[NoteRead]


class UserPage(Page):
    """A page of users."""

    items: list[UserRead]


ERROR_RESPONSES: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Insufficient permission"},
    404: {"model": ErrorResponse, "description": "Not found"},
    409: {"model": ErrorResponse, "description": "Conflict with existing state"},
    422: {"model": ErrorResponse, "description": "Validation failed"},
    500: {"model": ErrorResponse, "description": "Unhandled server error"},
}


# --- authentication ---


class UserRegister(BaseModel):
    """Registration payload.

    max_length is 72 because bcrypt operates on at most 72 bytes and raises
    beyond that. Without this the error surfaces as a 500 from the hashing
    call rather than a 422 naming the field.
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=80)


class PasswordChange(BaseModel):
    """Changing a password requires proving you know the current one."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=8, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def must_differ(cls, value, info):
        if value == info.data.get("current_password"):
            raise ValueError("new_password must differ from current_password")
        return value


class TokenPair(BaseModel):
    """The login response.

    token_type is "bearer" and access_token is spelled exactly that way because
    OAuth2 says so, and Swagger UI reads those names to wire up its Authorize
    button.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """A refresh token being exchanged for a new access token."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class RoleChange(BaseModel):
    """An admin changing someone's role."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "admin"]
