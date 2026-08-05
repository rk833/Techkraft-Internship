"""Request and response schemas.

The central idea of this module lives in this file: the shape a client sends is
not the shape the API returns. UserCreate has a password. UserRead does not,
and cannot, because the field is simply absent from the class.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Fields common to input and output.

    Kept in one place so a change to the username rules cannot apply to the
    request schema and be forgotten on the response schema.
    """

    username: str = Field(min_length=3, max_length=20, description="Unique login name")
    email: EmailStr = Field(description="Validated email address")
    full_name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=200)


class UserCreate(UserBase):
    """What the client sends to register.

    Adds the one field that must never travel in the other direction.
    """

    password: str = Field(min_length=8, max_length=72, description="Plain text, hashed in module 12")


class UserRead(UserBase):
    """What the API returns.

    There is no password field. This is not a filter that could be misconfigured
    or a flag that could be forgotten - the attribute does not exist on the
    class, so FastAPI has nothing to serialise even when handed a record that
    contains one.
    """

    id: int
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """A partial update. Every field is optional.

    This cannot inherit from UserBase, because UserBase makes username and email
    required. A PATCH body of {"bio": "..."} must be valid, so the optionality
    has to be redeclared. Repetitive, and the standard way to do it.
    """

    username: str | None = Field(default=None, min_length=3, max_length=20)
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=200)


class Message(BaseModel):
    """A plain acknowledgement, for endpoints with nothing else to return."""

    detail: str
