"""Dependencies, now including the authentication chain.

get_current_user is the piece everything else hangs off. Note that it does not
merely decode a token: it also confirms the user still exists and is still
active. A token is a claim made minutes ago, and a great deal can change in
minutes - the account can be deleted, disabled, or demoted.
"""

import logging
from typing import Annotated, Iterator

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.errors import ForbiddenError, NotFoundError, UnauthenticatedError
from app.models import Note, Role, User
from app.security import TokenError, decode_token

logger = logging.getLogger("api.deps")

# tokenUrl is what gives Swagger UI its Authorize button and tells it where to
# post the login form. It is documentation for the client, not a route this
# dependency calls.
#
# auto_error=False so a missing header raises our own UnauthenticatedError in
# the standard envelope, rather than FastAPI's bare {"detail": "Not
# authenticated"}.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_db() -> Iterator[Session]:
    """Provide a session for one request, then commit or roll back."""
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


DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class PaginationParams:
    """Pagination, carried over from module 09."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


Pagination = Annotated[PaginationParams, Depends(PaginationParams)]


def get_current_user(
    db: DbSession,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """Resolve the bearer token to a live user, or raise 401.

    Four separate checks, and every one of them matters:

    1. A token was supplied at all.
    2. It verifies against our key, has not expired, and is an access token
       rather than a refresh token.
    3. The user it names still exists.
    4. That user is still active.

    Steps 3 and 4 are the ones commonly skipped. Trusting the token alone means
    a deleted or suspended user keeps working until their token expires, which
    is precisely the window that matters when an account is disabled.
    """
    if not token:
        raise UnauthenticatedError("Not authenticated")

    try:
        claims = decode_token(token, expected_type="access", settings=settings)
    except TokenError as exc:
        # The reason is logged, not returned. "signature invalid" versus
        # "expired" is useful to us and useful to an attacker.
        logger.info("token rejected: %s", exc)
        raise UnauthenticatedError("Could not validate credentials") from exc

    user = db.get(User, int(claims["sub"]))
    if user is None:
        logger.warning("token names a user that no longer exists: %s", claims["sub"])
        raise UnauthenticatedError("Could not validate credentials")
    if not user.is_active:
        raise ForbiddenError("This account is disabled")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    """Allow only administrators through.

    403 rather than 401. The caller proved who they are; the answer is still
    no, and telling them to authenticate again cannot help.

    The role is re-read from the database row rather than taken from the
    token's role claim, so a demotion takes effect immediately instead of when
    the token expires.
    """
    if current_user.role != Role.ADMIN:
        logger.warning("user %s attempted an admin action", current_user.id)
        raise ForbiddenError("Administrator access is required")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


def get_own_note(note_id: int, db: DbSession, current_user: CurrentUser) -> Note:
    """Resolve {note_id} to a note the caller is allowed to touch.

    Authentication and authorisation in one dependency, because separating them
    here would mean every handler remembering to run the second check.

    A note owned by someone else returns 404, not 403. 403 would confirm that a
    note with that id exists, which lets an unauthorised caller enumerate the
    id space and learn how many notes the system holds. An admin is exempt.
    """
    note = db.get(Note, note_id)
    if note is None:
        raise NotFoundError(f"No note with id {note_id}")
    if note.author_id != current_user.id and current_user.role != Role.ADMIN:
        logger.warning("user %s attempted to access note %s", current_user.id, note_id)
        raise NotFoundError(f"No note with id {note_id}")
    return note


OwnNote = Annotated[Note, Depends(get_own_note)]


def get_user_or_404(user_id: int, db: DbSession) -> User:
    """Resolve {user_id} to a User, or raise the 404."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}")
    return user


UserDep = Annotated[User, Depends(get_user_or_404)]
