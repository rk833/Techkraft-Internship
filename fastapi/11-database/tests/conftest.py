"""Test fixtures for a database-backed API.

Two decisions here are the substance of the module's testing story.

1. The test schema is built by running the real Alembic migrations, not by
   Base.metadata.create_all(). create_all builds the schema from the models, so
   the tests would pass even if a migration were broken, missing, or had never
   been written. Migrating means the migrations are exercised on every run.

2. Each test runs inside a transaction that is rolled back afterwards. Nothing
   a test writes survives it, so tests are order-independent and the database
   is left exactly as it was found.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import configure_sqlite
from app.dependencies import get_db
from app.main import app

MODULE_ROOT = Path(__file__).resolve().parent.parent
settings = get_settings()
TEST_URL = settings.resolved_test_database_url


@pytest.fixture(scope="session")
def test_engine():
    """A separate database, migrated once for the whole session.

    Separate from the development database, so running the suite can never
    touch real data. The file is removed first and last, so a run always starts
    from nothing.
    """
    db_path = Path(TEST_URL.replace("sqlite:///", ""))
    db_path.unlink(missing_ok=True)

    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    # Identical treatment to the application engine. Foreign key enforcement
    # and, critically, transaction control - without the latter the rollback
    # below discards nothing and every test leaks its rows into the next.
    configure_sqlite(engine)

    alembic_cfg = Config(str(MODULE_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(MODULE_ROOT / "alembic"))
    # env.py reads this, so the migrations run against the test database
    # without any file being edited.
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    command.upgrade(alembic_cfg, "head")

    yield engine

    engine.dispose()
    os.environ.pop("ALEMBIC_DATABASE_URL", None)
    db_path.unlink(missing_ok=True)


@pytest.fixture
def db_connection(test_engine):
    """One connection with an open transaction, rolled back after the test.

    Everything in a test - the requests and the assertions - runs on this one
    connection, so they see each other's uncommitted work. Rolling back at the
    end discards all of it, which is what leaves the database untouched.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()


@pytest.fixture
def session_factory(db_connection):
    """Sessions bound to the test connection.

    join_transaction_mode="create_savepoint" is what makes this work. A session
    bound to a connection that already has a transaction would otherwise join
    it, and the first commit() inside a request would end the outer transaction
    - leaving the rollback with nothing to undo and the data committed for
    real. With create_savepoint, each session opens a SAVEPOINT instead, so
    commit() behaves normally from the application's point of view while the
    outer rollback still discards everything.
    """
    return sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
def db_session(session_factory) -> Session:
    """A session for the test's own assertions, separate from the requests'."""
    session = session_factory()
    yield session
    session.close()


def _install_override(session_factory) -> None:
    """Point get_db at the test connection, one session per request.

    A fresh session per request rather than one shared session, because that is
    what production does. Sharing one made two tests pass for the wrong reason
    and two others fail for the wrong reason: a deleted row stayed visible
    through the identity map, and one request's rollback undid an earlier
    request's work.
    """

    def override_get_db():
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        else:
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client(session_factory):
    """A TestClient wired to the transactional test connection.

    get_db is replaced rather than the engine being reconfigured, which is the
    seam module 09 built. The application code is unchanged and unaware.
    """
    _install_override(session_factory)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def raw_client(session_factory):
    """The same, but returning 500 responses rather than re-raising."""
    _install_override(session_factory)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(client) -> dict:
    """One created user."""
    response = client.post(
        "/users",
        json={"username": "ada", "email": "ada@example.com", "full_name": "Ada Lovelace"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def other_user(client) -> dict:
    """A second user, for ownership and isolation checks."""
    response = client.post("/users", json={"username": "grace", "email": "grace@example.com"})
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def notes(client, user) -> list[dict]:
    """Three notes belonging to the first user."""
    created = []
    for i in range(3):
        response = client.post(
            f"/users/{user['id']}/notes",
            json={"title": f"Note number {i}", "body": f"Body of note {i}."},
        )
        assert response.status_code == 201
        created.append(response.json())
    return created


class QueryCounter:
    """Counts SQL statements issued while it is active.

    The only way to demonstrate an N+1 problem is to count queries. Timing is
    too noisy at this scale, and reading the code is exactly what fails to spot
    it in the first place.
    """

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._record)

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    @property
    def count(self) -> int:
        return len(self.statements)

    def count_of(self, keyword: str) -> int:
        return sum(1 for s in self.statements if s.lstrip().upper().startswith(keyword.upper()))


@pytest.fixture
def query_counter(test_engine):
    """Factory for the query counter, bound to the test engine."""
    return lambda: QueryCounter(test_engine)


def pytest_collection_modifyitems(items):
    """Reverse collection order when REVERSE_TESTS is set."""
    if os.environ.get("REVERSE_TESTS"):
        items.reverse()
