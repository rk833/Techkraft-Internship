"""Shared test fixtures.

Two clients here, and the difference matters for this module. TestClient is
synchronous: it drives the app from a worker thread, so it cannot issue two
overlapping requests. Anything measuring concurrency needs a real
httpx.AsyncClient driving the app over ASGITransport from the test's own event
loop.
"""

import os

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from clients import close_client, open_client
from config import get_settings
from main import app


@pytest.fixture
def client():
    """Synchronous client, for correctness tests.

    Used as a context manager so lifespan runs and the shared HTTP client
    exists. Without that, every aggregation endpoint fails on get_client.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def aclient():
    """Asynchronous client, for concurrency tests.

    The application lifespan is invoked by hand rather than by a context
    manager, because httpx.ASGITransport does not run lifespan events. Missing
    this produces a RuntimeError from get_client that looks unrelated to the
    cause, which is why get_client's message says so explicitly.
    """
    await open_client(get_settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0
    ) as async_client:
        yield async_client
    await close_client()


def pytest_collection_modifyitems(items):
    """Reverse collection order when REVERSE_TESTS is set."""
    if os.environ.get("REVERSE_TESTS"):
        items.reverse()
