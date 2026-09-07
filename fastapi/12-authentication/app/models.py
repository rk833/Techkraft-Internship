"""ORM models.

SQLAlchemy 2.0 declarative style: Mapped[] annotations plus mapped_column().
The annotation is the source of truth for both the Python type and, where it can
be inferred, the column type - the same idea as FastAPI reading its validation
from a signature.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(str, Enum):
    """The roles a user can hold.

    Stored as a plain string column rather than a database enum type. Adding a
    role then needs no migration, and ALTER TYPE for a native enum is awkward
    on PostgreSQL and unsupported on SQLite.
    """

    USER = "user"
    ADMIN = "admin"


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    datetime.utcnow() is deprecated in 3.12 and returns a naive datetime, which
    compares incorrectly against aware ones and silently loses the offset on the
    way into the database.
    """
    return datetime.now(timezone.utc)


class User(Base):
    """A person who owns notes."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True creates a database-level constraint, which is the only place
    # uniqueness can actually be guaranteed. A check in application code loses
    # to two concurrent requests.
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(80), default=None)
    # The bcrypt hash, never the password. 60 characters is the fixed width of
    # a bcrypt hash; String(128) leaves room for a future algorithm change.
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user", index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    @property
    def is_admin(self) -> bool:
        """True when this user holds the admin role."""
        return self.role == Role.ADMIN

    # back_populates on both sides keeps the two directions in sync in memory.
    # cascade="all, delete-orphan" makes deleting a user delete their notes
    # through the ORM; passive_deletes with ondelete="CASCADE" on the foreign
    # key lets the database do it in one statement instead of N.
    notes: Mapped[list["Note"]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class Note(Base):
    """A note belonging to exactly one user."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    # Added by the second migration, after the table already existed. NOT NULL
    # with a server_default, so the ALTER can fill the existing rows - adding a
    # NOT NULL column without one fails against any table that has data.
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    # ondelete="CASCADE" is the database-side rule. Without it, the ORM cascade
    # still works but a raw SQL delete would leave orphans, and the constraint
    # would reject the delete outright.
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now()
    )

    author: Mapped["User"] = relationship(back_populates="notes")

    # A composite index for the most common query: this user's notes, newest
    # first. Declared here rather than in a migration by hand so that
    # autogenerate can see it and keep the two in step.
    __table_args__ = (Index("ix_notes_author_created", "author_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<Note id={self.id} title={self.title!r}>"
