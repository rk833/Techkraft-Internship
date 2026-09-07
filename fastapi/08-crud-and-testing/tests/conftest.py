"""Shared test fixtures.

conftest.py is discovered automatically by pytest. Fixtures defined here are
available to every test module in this directory without being imported.
"""

import os

import pytest
from fastapi.testclient import TestClient

from main import app
from store import store


@pytest.fixture(autouse=True)
def reset_store():
    """Restore the store to its seeded state before every single test.

    autouse=True means no test has to remember to ask for it. This one fixture
    is what makes the suite order-independent: without it, a test that creates
    or deletes a task silently changes what every later test sees, and the
    suite only passes in the order it was written in.
    """
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    """A TestClient that runs the application lifespan.

    Used as a context manager on purpose. TestClient(app) without `with` never
    triggers startup or shutdown, so anything created in lifespan would be
    missing and the failure would look unrelated.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def raw_client():
    """A client that returns 500 responses instead of re-raising.

    The default TestClient re-raises a server exception into the test, so the
    catch-all handler and the middleware around it are never exercised. Any
    test asserting on a 500 needs this one.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def new_task(client):
    """Create a task and return it, for tests that need one that is not seeded."""
    response = client.post("/tasks", json={"title": "Fixture created task", "priority": "low"})
    assert response.status_code == 201
    return response.json()


def pytest_collection_modifyitems(items):
    """Reverse the collection order when REVERSE_TESTS is set.

    Exists so order independence can be demonstrated rather than asserted:
    running the suite normally and again with REVERSE_TESTS=1 exercises the
    tests in opposite orders. A suite depending on execution order fails one of
    the two runs.
    """
    if os.environ.get("REVERSE_TESTS"):
        items.reverse()
