"""Test fixtures.

Carried over from module 11, plus authenticated clients. bcrypt_rounds is
dropped to 4 for the suite: at the production cost of 12, the ~60 hashes these
tests perform would add roughly twelve seconds.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.database import configure_sqlite
from app.dependencies import get_db
from app.main import app
from app.models import Role, User
from app.security import hash_password

MODULE_ROOT = Path(__file__).resolve().parent.parent

# A dedicated settings object for the suite. Overriding get_settings rather
# than mutating the real one keeps the production configuration untouched.
TEST_SETTINGS = Settings(bcrypt_rounds=4)
TEST_URL = TEST_SETTINGS.resolved_test_database_url


@pytest.fixture(autouse=True)
def use_test_settings():
    """Point every get_settings dependency at the fast test settings."""
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def test_engine():
    """A separate database, migrated once for the whole session."""
    db_path = Path(TEST_URL.replace("sqlite:///", ""))
    db_path.unlink(missing_ok=True)

    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    configure_sqlite(engine)

    alembic_cfg = Config(str(MODULE_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(MODULE_ROOT / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    command.upgrade(alembic_cfg, "head")

    yield engine

    engine.dispose()
    os.environ.pop("ALEMBIC_DATABASE_URL", None)
    db_path.unlink(missing_ok=True)


@pytest.fixture
def db_connection(test_engine):
    """One connection with an open transaction, rolled back after the test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()


@pytest.fixture
def session_factory(db_connection):
    """Sessions bound to the test connection, each in its own SAVEPOINT."""
    return sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
def db_session(session_factory) -> Session:
    """A session for the test's own assertions."""
    session = session_factory()
    yield session
    session.close()


def _install_override(session_factory) -> None:
    """Point get_db at the test connection, one session per request."""

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
    """An unauthenticated TestClient."""
    _install_override(session_factory)
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def raw_client(session_factory):
    """The same, but returning 500 responses rather than re-raising."""
    _install_override(session_factory)
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- account fixtures -----------------------------------------------------

ALICE = {"username": "alice", "email": "alice@example.com", "password": "alice-password-1"}
BOB = {"username": "bob", "email": "bob@example.com", "password": "bob-password-1"}


def _register(client, credentials: dict) -> dict:
    response = client.post("/auth/register", json=credentials)
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, credentials: dict) -> dict:
    """Log in using the OAuth2 form encoding, as a real client would."""
    response = client.post(
        "/auth/login",
        data={"username": credentials["username"], "password": credentials["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def alice(client) -> dict:
    """A registered user with tokens."""
    account = _register(client, ALICE)
    tokens = _login(client, ALICE)
    return {**account, **tokens, "credentials": ALICE}


@pytest.fixture
def bob(client) -> dict:
    """A second registered user, for cross-account checks."""
    account = _register(client, BOB)
    tokens = _login(client, BOB)
    return {**account, **tokens, "credentials": BOB}


@pytest.fixture
def admin(client, db_session) -> dict:
    """An administrator.

    Created directly in the database rather than through an endpoint, because
    there is deliberately no route that grants the first admin role. Promoting
    yourself over HTTP is the hole this avoids; bootstrapping happens out of
    band.
    """
    user = User(
        username="root",
        email="root@example.com",
        hashed_password=hash_password("root-password-1", TEST_SETTINGS),
        role=Role.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    tokens = _login(client, {"username": "root", "password": "root-password-1"})
    return {"id": user.id, **tokens}


def auth(token_holder: dict) -> dict:
    """Build the Authorization header for a fixture's access token."""
    return {"Authorization": f"Bearer {token_holder['access_token']}"}


@pytest.fixture
def alice_notes(client, alice) -> list[dict]:
    """Three notes belonging to alice."""
    created = []
    for i in range(3):
        response = client.post("/notes", json={"title": f"Alice note {i}"}, headers=auth(alice))
        assert response.status_code == 201
        created.append(response.json())
    return created


def pytest_collection_modifyitems(items):
    """Reverse collection order when REVERSE_TESTS is set."""
    if os.environ.get("REVERSE_TESTS"):
        items.reverse()
