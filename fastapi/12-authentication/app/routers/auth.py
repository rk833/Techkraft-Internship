"""Authentication routes.

Every handler here is a plain `def`, not `async def`. bcrypt is deliberately
expensive CPU work - roughly 200ms at cost factor 12 - and module 10 measured
what that does to an event loop. A `def` endpoint runs in the threadpool, so a
slow login blocks a worker thread instead of the whole server.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import CurrentUser, DbSession, SettingsDep
from app.errors import ConflictError, UnauthenticatedError
from app.models import Role, User
from app.schemas import (
    ERROR_RESPONSES,
    PasswordChange,
    RefreshRequest,
    TokenPair,
    UserRead,
    UserRegister,
)
from app.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)

logger = logging.getLogger("api.auth")

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)


def _issue_tokens(user: User, settings) -> dict:
    """Mint an access and a refresh token for a user."""
    return {
        "access_token": create_token(user.id, "access", user.role, settings),
        "refresh_token": create_token(user.id, "refresh", user.role, settings),
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
def register(payload: UserRegister, db: DbSession, settings: SettingsDep) -> User:
    """Create an account.

    The plain password exists only as a local variable and is hashed before
    anything is stored. It is never logged, never assigned to the model, and
    never returned - UserRead has no field for it.
    """
    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password, settings),
        role=Role.USER,
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError as exc:
        # The message is deliberately vague about which field collided.
        # "That email is taken" is a free account-existence oracle.
        raise ConflictError("That username or email is already registered") from exc

    logger.info("registered user %s", user.id)
    return user


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for tokens")
def login(
    db: DbSession,
    settings: SettingsDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> dict:
    """Log in and receive an access and refresh token pair.

    The body is form-encoded rather than JSON, with fields named `username` and
    `password`. That is the OAuth2 password flow, and matching it is what lets
    Swagger UI's Authorize button work without any custom wiring.

    One failure message for every failure. Distinguishing "no such user" from
    "wrong password" tells an attacker which usernames are real.
    """
    user = db.scalars(select(User).where(User.username == form.username)).first()

    # verify_password runs even when the user does not exist, against a dummy
    # hash. Returning early would make an unknown username measurably faster
    # than a wrong password, which is enough to enumerate accounts.
    if not verify_password(form.password, user.hashed_password if user else None, settings):
        logger.info("failed login for username=%r", form.username)
        raise UnauthenticatedError("Incorrect username or password")

    if not user.is_active:
        raise UnauthenticatedError("Incorrect username or password")

    # The one moment the plain password is available, so the only moment an old
    # hash can be upgraded to the current cost factor.
    if needs_rehash(user.hashed_password, settings):
        logger.info("upgrading password hash for user %s", user.id)
        user.hashed_password = hash_password(form.password, settings)

    logger.info("user %s logged in", user.id)
    return _issue_tokens(user, settings)


@router.post("/refresh", response_model=TokenPair, summary="Exchange a refresh token")
def refresh(payload: RefreshRequest, db: DbSession, settings: SettingsDep) -> dict:
    """Trade a valid refresh token for a fresh pair.

    decode_token insists on type="refresh", so an access token cannot be used
    here. The reverse check matters more: get_current_user insists on
    type="access", so a long-lived refresh token cannot be presented as
    authorisation to a normal endpoint.

    The user is re-read rather than trusted from the token, so a deleted or
    disabled account cannot refresh its way into a new session.
    """
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh", settings=settings)
    except TokenError as exc:
        raise UnauthenticatedError("Invalid refresh token") from exc

    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise UnauthenticatedError("Invalid refresh token")

    return _issue_tokens(user, settings)


@router.get("/me", response_model=UserRead, summary="The authenticated user")
def me(current_user: CurrentUser) -> User:
    """Return the caller's own account.

    The entire body is one return statement. Everything that makes this
    endpoint secure happened in the dependency.
    """
    return current_user


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change your own password",
)
def change_password(
    payload: PasswordChange,
    current_user: CurrentUser,
    settings: SettingsDep,
) -> None:
    """Change the caller's password.

    The current password is required even though the caller is already
    authenticated. A stolen access token should not be enough to take
    permanent ownership of an account.
    """
    if not verify_password(payload.current_password, current_user.hashed_password, settings):
        logger.warning("failed password change for user %s", current_user.id)
        raise UnauthenticatedError("Current password is incorrect")

    current_user.hashed_password = hash_password(payload.new_password, settings)
    logger.info("password changed for user %s", current_user.id)
