"""Note routes, including a deliberate demonstration of the N+1 problem."""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, NoteDep, Pagination, UserDep
from app.models import Note
from app.schemas import (
    ERROR_RESPONSES,
    NoteCreate,
    NotePage,
    NoteRead,
    NoteUpdate,
    NoteWithAuthor,
)

router = APIRouter(tags=["notes"], responses=ERROR_RESPONSES)


@router.post(
    "/users/{user_id}/notes",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note for a user",
)
def create_note(user: UserDep, payload: NoteCreate, db: DbSession) -> Note:
    """Create a note.

    Assigning through the relationship rather than setting author_id by hand
    means SQLAlchemy fills the foreign key, and a user that does not exist has
    already produced a 404 in the dependency.
    """
    note = Note(**payload.model_dump(), author=user)
    db.add(note)
    db.flush()
    return note


@router.get("/users/{user_id}/notes", response_model=NotePage, summary="List a user's notes")
def list_user_notes(
    user: UserDep,
    db: DbSession,
    page: Pagination,
    archived: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
) -> dict:
    """Return a filtered page of one user's notes.

    Filters are applied in SQL, not in Python. Loading every note and filtering
    with a list comprehension gives the same answer and transfers the whole
    table to do it.
    """
    conditions = [Note.author_id == user.id]
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


@router.get("/notes", response_model=list[NoteWithAuthor], summary="All notes with authors (N+1)")
def list_notes_n_plus_one(db: DbSession, page: Pagination) -> list[Note]:
    """List notes with their authors, badly.

    Deliberately wrong. The query fetches notes only; the response model then
    reads note.author on each one, and each of those reads is a separate SELECT
    that SQLAlchemy issues lazily.

    One query for the page plus one per row. At 20 rows that is 21 queries for
    data that fits in one. The endpoint below is the same thing done correctly,
    and the tests count the statements for both.
    """
    return list(
        db.scalars(select(Note).order_by(Note.id).limit(page.limit).offset(page.offset)).all()
    )


@router.get(
    "/notes/eager",
    response_model=list[NoteWithAuthor],
    summary="All notes with authors (eager loaded)",
)
def list_notes_eager(db: DbSession, page: Pagination) -> list[Note]:
    """The same result, without the N+1.

    selectinload issues one extra SELECT that fetches every needed author with
    a single WHERE id IN (...). Two queries regardless of page size.

    joinedload is the other option: one query with a JOIN. selectinload is
    usually better for a collection because a JOIN duplicates the parent row
    once per child.
    """
    return list(
        db.scalars(
            select(Note)
            .options(selectinload(Note.author))
            .order_by(Note.id)
            .limit(page.limit)
            .offset(page.offset)
        ).all()
    )


@router.get("/notes/{note_id}", response_model=NoteRead, summary="Get one note")
def get_note(note: NoteDep) -> Note:
    """Return a single note."""
    return note


@router.patch("/notes/{note_id}", response_model=NoteRead, summary="Update a note")
def update_note(note: NoteDep, payload: NoteUpdate, db: DbSession) -> Note:
    """Update only the fields the client sent.

    No db.add() and no explicit UPDATE. The note is already tracked by the
    session, so mutating an attribute is enough - SQLAlchemy works out what
    changed and emits the statement at flush time.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    db.flush()
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note")
def delete_note(note: NoteDep, db: DbSession) -> None:
    """Delete a note."""
    db.delete(note)
