"""Dependencies.

get_db is module 09's UnitOfWork made real: same shape, same commit-on-success
and rollback-on-failure, now wrapping an actual database transaction.
"""

import logging
from typing import Annotated, Iterator

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.errors import NotFoundError
from app.models import Note, User

logger = logging.getLogger("api.deps")


def get_db() -> Iterator[Session]:
    """Provide a session for one request, then commit or roll back.

    Every request gets its own session and its own connection. A module-level
    session shared between requests would interleave two users' work into one
    transaction, which is a data corruption bug rather than a style problem.

    Committing here rather than in each endpoint means no handler can forget,
    and a handler that raises halfway through cannot leave a partial write
    behind. Module 09 measured that this rollback fires for a deliberately
    raised 404 as well as for an unexpected exception.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    else:
        session.commit()
    finally:
        # Returns the connection to the pool. Skipping this exhausts the pool
        # after pool_size + max_overflow requests, and the symptom is the whole
        # application hanging rather than an error.
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


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


def get_user_or_404(user_id: int, db: DbSession) -> User:
    """Resolve {user_id} to a User, or raise the 404."""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"No user with id {user_id}")
    return user


def get_note_or_404(note_id: int, db: DbSession) -> Note:
    """Resolve {note_id} to a Note, or raise the 404.

    db.get() is a primary-key lookup that checks the session's identity map
    first, so fetching the same row twice in one request does not hit the
    database twice.
    """
    note = db.get(Note, note_id)
    if note is None:
        raise NotFoundError(f"No note with id {note_id}")
    return note


UserDep = Annotated[User, Depends(get_user_or_404)]
NoteDep = Annotated[Note, Depends(get_note_or_404)]
