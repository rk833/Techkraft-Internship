"""Engine, session factory, and declarative base.

This module knows how to connect. It does not know what the tables are - that is
models.py - and it does not know when a session begins or ends - that is the
dependency in dependencies.py. Keeping those three separate is what lets Alembic
import the metadata without importing the web application.
"""

import logging

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("api.database")

settings = get_settings()


def _engine_kwargs(url: str) -> dict:
    """Connection arguments that differ between SQLite and everything else."""
    if url.startswith("sqlite"):
        return {
            # SQLite refuses to use a connection from a thread other than the
            # one that opened it. FastAPI runs sync endpoints in a threadpool,
            # so that check has to be relaxed. It is safe here because the
            # session dependency gives each request its own connection.
            #
            # This is a SQLite quirk, not a general pattern. Setting it against
            # PostgreSQL would be meaningless.
            "connect_args": {"check_same_thread": False},
        }
    return {
        # Sensible pool settings for a real database. SQLite ignores these.
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }


engine = create_engine(
    settings.resolved_database_url,
    echo=settings.database_echo,
    **_engine_kwargs(settings.resolved_database_url),
)

# expire_on_commit=False matters for an API. With the default, every attribute
# of a committed object is invalidated, so reading `note.id` after commit fires
# a fresh SELECT - and if the session is already closed, raises instead. Since
# the response model reads attributes after the dependency commits, leaving this
# at its default produces a confusing DetachedInstanceError.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for every model.

    SQLAlchemy 2.0 style. The 1.x equivalent was declarative_base(), and older
    tutorials still use it - along with Column() instead of mapped_column() and
    no Mapped[] annotations.
    """


def configure_sqlite(target_engine: Engine) -> None:
    """Apply the two SQLite fixes every SQLAlchemy project needs.

    Both are no-ops on any other database, and both cause silent wrong
    behaviour on SQLite if omitted. Exposed as a function so the test engine
    gets exactly the same treatment as the application engine.
    """
    if target_engine.dialect.name != "sqlite":
        return

    @event.listens_for(target_engine, "connect")
    def _on_connect(dbapi_connection, connection_record) -> None:
        # 1. SQLite does not enforce foreign keys unless asked, per connection.
        #    Without this a cascade delete silently does nothing and orphaned
        #    rows accumulate - and the same code against PostgreSQL, which does
        #    enforce them, behaves differently.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

        # 2. The pysqlite driver manages transactions itself and does not emit
        #    BEGIN where SQLAlchemy expects one. Setting isolation_level=None
        #    turns that off so SQLAlchemy is in charge.
        #
        #    This is not academic. Without it, connection.begin() does not open
        #    a real transaction, so a later rollback() discards nothing. A
        #    transactional test fixture appears to isolate each test and in
        #    fact leaks every row - measured here as data surviving an explicit
        #    rollback.
        dbapi_connection.isolation_level = None

    @event.listens_for(target_engine, "begin")
    def _on_begin(connection) -> None:
        """Emit the BEGIN that the driver no longer sends."""
        connection.exec_driver_sql("BEGIN")


configure_sqlite(engine)


def session_scope() -> Session:
    """Return a new session. For scripts and tests, not for request handling."""
    return SessionLocal()
