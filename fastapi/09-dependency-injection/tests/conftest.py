"""Shared test fixtures."""

import os

import pytest
from fastapi.testclient import TestClient

import dependencies as deps
from config import Settings
from main import app
from store import store


@pytest.fixture(autouse=True)
def reset_state():
    """Restore the store, the event log, and any dependency overrides.

    Clearing dependency_overrides is the part that is easy to forget and
    catastrophic to skip. An override left behind leaks into every later test
    in the session, and the resulting failure points at whichever test ran next
    rather than at the one that set it.
    """
    store.reset()
    deps.EVENTS.clear()
    app.dependency_overrides.clear()
    yield
    store.reset()
    deps.EVENTS.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """A TestClient that runs the application lifespan."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def raw_client():
    """A client that returns 500 responses instead of re-raising them."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def admin_headers():
    """Headers carrying the real admin key from settings."""
    return {"X-API-Key": Settings().admin_api_key}


class FakeStore:
    """A stand-in for TaskStore, holding two fixed tasks.

    Deliberately not a subclass. The endpoints depend on get_store returning
    something with the right methods, not on a particular class, so this proves
    the seam is real rather than a subclass hook.
    """

    def __init__(self, tasks: list[dict] | None = None) -> None:
        self.tasks = tasks if tasks is not None else [
            {
                "id": 101, "title": "Fake task one", "description": None,
                "status": "todo", "priority": "high", "tags": ["fake"],
                "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 102, "title": "Fake task two", "description": "From the fake store.",
                "status": "done", "priority": "low", "tags": ["fake", "other"],
                "created_at": "2026-01-02T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
            },
        ]

    def list(self) -> list[dict]:
        return list(self.tasks)

    def get(self, task_id: int) -> dict | None:
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def find_by_title(self, title: str) -> dict | None:
        return next((t for t in self.tasks if t["title"] == title), None)


@pytest.fixture
def fake_store():
    """A FakeStore instance for tests to inject."""
    return FakeStore()


def pytest_collection_modifyitems(items):
    """Reverse collection order when REVERSE_TESTS is set."""
    if os.environ.get("REVERSE_TESTS"):
        items.reverse()
