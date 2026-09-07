"""User routes."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, status

from app.dependencies import DbSession, Pagination, UserDep
from app.errors import ConflictError
from app.models import Note, User
from app.schemas import ERROR_RESPONSES, UserCreate, UserPage, UserRead, UserWithCount

router = APIRouter(prefix="/users", tags=["users"], responses=ERROR_RESPONSES)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED, summary="Register a user")
def create_user(payload: UserCreate, db: DbSession) -> User:
    """Create a user.

    The uniqueness check is the database's, not ours. Querying first and then
    inserting looks tidier and is a race: two concurrent requests both see no
    existing row and both insert. Catching IntegrityError is the only version
    that is actually correct.

    flush() sends the INSERT without committing, so the constraint fires here
    where it can be turned into a 409, rather than in the dependency's commit
    where it would surface as an unhandled 500.
    """
    user = User(**payload.model_dump())
    try:
        # begin_nested() opens a SAVEPOINT. On failure only the work inside it
        # is undone, leaving the surrounding transaction intact.
        #
        # A bare db.rollback() here would discard the entire transaction,
        # including anything the request had already done. A test caught this:
        # a rejected duplicate wiped a user created earlier in the same
        # transaction, which is exactly what would happen in production to any
        # work preceding a caught IntegrityError.
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "That username or email is already registered",
            details=[{"field": "body.username", "message": "must be unique", "type": "duplicate"}],
        ) from exc
    return user


@router.get("", response_model=UserPage, summary="List users")
def list_users(db: DbSession, page: Pagination) -> dict:
    """Return a page of users.

    Two statements: one COUNT for the total, one SELECT for the page. Counting
    by loading every row and calling len() would work at this size and fall
    over at a million.
    """
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(
        select(User).order_by(User.id).limit(page.limit).offset(page.offset)
    ).all()
    return {
        "total": total,
        "count": len(users),
        "limit": page.limit,
        "offset": page.offset,
        "items": users,
    }


@router.get("/{user_id}", response_model=UserWithCount, summary="Get one user")
def get_user(user: UserDep, db: DbSession) -> dict:
    """Return a user and how many notes they have.

    The count is a COUNT query rather than len(user.notes), which would load
    every note row into memory to discard all but the number.
    """
    note_count = db.scalar(
        select(func.count()).select_from(Note).where(Note.author_id == user.id)
    ) or 0
    return {**UserRead.model_validate(user).model_dump(), "note_count": note_count}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user")
def delete_user(user: UserDep, db: DbSession) -> None:
    """Delete a user and, by cascade, all of their notes."""
    db.delete(user)
