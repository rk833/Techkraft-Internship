"""Note routes, now scoped to the authenticated user.

The change from module 11 is that no endpoint takes a user id any more. The
owner is whoever holds the token, so there is no parameter a client could
tamper with. Module 11's `/users/{user_id}/notes` was an authorisation hole
waiting for authentication to exist.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DbSession, OwnNote, Pagination
from app.models import Note
from app.schemas import (
    ERROR_RESPONSES,
    NoteCreate,
    NotePage,
    NoteRead,
    NoteUpdate,
    NoteWithAuthor,
)

router = APIRouter(prefix="/notes", tags=["notes"], responses=ERROR_RESPONSES)


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED, summary="Create a note")
def create_note(payload: NoteCreate, current_user: CurrentUser, db: DbSession) -> Note:
    """Create a note owned by the caller.

    author_id is taken from the token, not from the body. NoteCreate has no
    author_id field, so a client cannot create a note attributed to someone
    else - the same "the field does not exist" guarantee as module 04.
    """
    note = Note(**payload.model_dump(), author=current_user)
    db.add(note)
    db.flush()
    return note


@router.get("", response_model=NotePage, summary="List your own notes")
def list_my_notes(
    current_user: CurrentUser,
    db: DbSession,
    page: Pagination,
    archived: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
) -> dict:
    """Return the caller's notes.

    The ownership filter is part of the WHERE clause rather than a check
    applied afterwards. Filtering after the query would still work and would
    leak through pagination: a page of 20 could return 3 rows once someone
    else's were removed.
    """
    conditions = [Note.author_id == current_user.id]
    if archived is not None:
        conditions.append(Note.archived.is_(archived))
    if q is not None:
        conditions.append(Note.title.ilike(f"%{q}%"))

    total = db.scalar(select(func.count()).select_from(Note).where(*conditions)) or 0
    notes = db.scalars(
        select(Note)
        .where(*conditions)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return {
        "total": total,
        "count": len(notes),
        "limit": page.limit,
        "offset": page.offset,
        "items": notes,
    }


@router.get("/detailed", response_model=list[NoteWithAuthor], summary="Your notes with author")
def list_my_notes_detailed(current_user: CurrentUser, db: DbSession, page: Pagination) -> list[Note]:
    """Eager loaded, as established in module 11."""
    return list(
        db.scalars(
            select(Note)
            .where(Note.author_id == current_user.id)
            .options(selectinload(Note.author))
            .order_by(Note.id)
            .limit(page.limit)
            .offset(page.offset)
        ).all()
    )


@router.get("/{note_id}", response_model=NoteRead, summary="Get one of your notes")
def get_note(note: OwnNote) -> Note:
    """Return a note the caller owns.

    The 404 for someone else's note, rather than a 403, is deliberate. See the
    note on get_own_note in dependencies.py.
    """
    return note


@router.patch("/{note_id}", response_model=NoteRead, summary="Update one of your notes")
def update_note(note: OwnNote, payload: NoteUpdate, db: DbSession) -> Note:
    """Update only the fields the caller sent."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    db.flush()
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete one of your notes")
def delete_note(note: OwnNote, db: DbSession) -> None:
    """Delete a note the caller owns."""
    db.delete(note)
