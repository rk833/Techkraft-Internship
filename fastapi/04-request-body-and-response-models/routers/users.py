"""User routes.

Every route declares response_model. The handlers return raw dicts straight
from the store - dicts that contain a password and an internal_note - and the
response model is what decides that neither reaches the client.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, status

import data
from schemas import Message, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

UserId = Annotated[int, Path(ge=1, description="User id")]


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
)
def create_user(payload: UserCreate) -> dict:
    """Register a new user.

    Contrast with module 02, where the equivalent handler took an untyped dict
    and happily stored a numeric title. Here the body is a UserCreate, so a
    short password, a malformed email or a missing username is a 422 before
    this line runs.
    """
    if data.find_by_username(payload.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken")
    if data.find_by_email(payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is registered")

    user = {
        **payload.model_dump(),
        "id": data.next_id(),
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "internal_note": "self-registered",
    }
    data.users[user["id"]] = user
    # The password is still in this dict. response_model=UserRead removes it.
    return user


@router.get("", response_model=list[UserRead], summary="List users")
def list_users() -> list[dict]:
    """Return every user.

    response_model works elementwise over a list, so each record is filtered
    down to UserRead rather than the list being passed through whole.
    """
    return list(data.users.values())


@router.get(
    "/{user_id}",
    response_model=UserRead,
    responses={404: {"model": Message, "description": "No such user"}},
    summary="Get one user",
)
def get_user(user_id: UserId) -> dict:
    """Return a single user.

    The responses= argument documents the 404 shape in Swagger. Without it the
    docs would claim this endpoint only ever returns a UserRead, which is a lie
    the generated schema would happily tell.
    """
    user = data.users.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")
    return user


@router.get(
    "/{user_id}/profile",
    response_model=UserRead,
    response_model_exclude_none=True,
    summary="Get a user's public profile",
)
def get_user_profile(user_id: UserId) -> dict:
    """Return a user with null fields omitted entirely.

    Same response model as the endpoint above, one flag different. A user with
    no bio gets a response with no bio key, rather than "bio": null. Useful when
    the consumer treats a missing key and a null differently, or when payload
    size matters.
    """
    user = data.users.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")
    return user


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user")
def update_user(user_id: UserId, payload: UserUpdate) -> dict:
    """Update only the fields the client actually sent.

    model_dump(exclude_unset=True) is the load-bearing part. Without it the
    dump would include every unsent field as None, and a PATCH of
    {"bio": "hello"} would silently wipe full_name and email.

    exclude_unset distinguishes "the client omitted this" from "the client
    explicitly sent null", which a plain optional-with-default cannot.
    """
    user = data.users.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")

    changes = payload.model_dump(exclude_unset=True)
    if "username" in changes and changes["username"] != user["username"]:
        if data.find_by_username(changes["username"]):
            raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken")
    user.update(changes)
    return user


@router.post(
    "/{user_id}/change-password",
    response_model=Message,
    summary="Change a password",
)
def change_password(
    user_id: UserId,
    # Two scalar body parameters. With more than one, FastAPI stops treating
    # each as the whole body and nests them under their parameter names, so the
    # expected payload is {"current_password": "...", "new_password": "..."}.
    current_password: Annotated[str, Body(min_length=8, max_length=72)],
    new_password: Annotated[str, Body(min_length=8, max_length=72)],
) -> dict:
    """Change a user's password.

    Returns a Message rather than a UserRead. There is no reason for a password
    change to hand back the whole user record.
    """
    user = data.users.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")
    if user["password"] != current_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    if new_password == current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "New password must differ")

    user["password"] = new_password
    return {"detail": "Password updated"}


@router.post(
    "/{user_id}/deactivate",
    response_model=UserRead,
    summary="Deactivate a user",
)
def deactivate_user(
    user_id: UserId,
    # A single body parameter would normally be the entire request body, so
    # sending {"reason": "..."} would fail. embed=True forces the nesting that
    # two or more parameters get automatically.
    reason: Annotated[str, Body(embed=True, min_length=3, max_length=120)],
) -> dict:
    """Mark a user inactive and record why."""
    user = data.users.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")
    user["is_active"] = False
    user["internal_note"] = f"deactivated: {reason}"
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user")
def delete_user(user_id: UserId) -> None:
    """Delete a user.

    No response_model, because 204 means there is no body to model.
    """
    if user_id not in data.users:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No user with id {user_id}")
    del data.users[user_id]
