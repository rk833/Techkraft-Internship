"""The shared HTTP client.

One AsyncClient for the whole process, created at startup and closed at
shutdown. This is what module 07's lifespan section was building towards.

Creating a client per request is the most common performance mistake in async
Python. Each new client opens a fresh connection pool, so every call pays for a
TCP handshake and a TLS negotiation that a reused client would have avoided.
"""

import logging

import httpx

from config import Settings
from upstream import app as upstream_app

logger = logging.getLogger("api.clients")

# Module-level rather than passed around, because the lifespan creates it and
# a dependency reads it. Guarded by the dependency so a missing client is a
# clear error rather than an AttributeError deep in a request.
_client: httpx.AsyncClient | None = None


def build_client(settings: Settings) -> httpx.AsyncClient:
    """Create the client, choosing a transport from configuration.

    With no upstream_base_url the client talks to the upstream ASGI app
    directly, in-process, with no socket involved. The calls are still real
    httpx calls and still genuinely concurrent - ASGITransport awaits the app
    the same way a network transport awaits a socket.

    That makes the tests fast and deterministic without replacing httpx with a
    mock, so the code under test is the code that runs in production.
    """
    timeout = httpx.Timeout(settings.upstream_timeout_seconds)
    if settings.upstream_base_url:
        logger.info("upstream over http: %s", settings.upstream_base_url)
        return httpx.AsyncClient(base_url=settings.upstream_base_url, timeout=timeout)

    logger.info("upstream in-process via ASGITransport")
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=upstream_app),
        base_url="http://upstream",
        timeout=timeout,
    )


async def open_client(settings: Settings) -> None:
    """Create the process-wide client. Called from lifespan startup."""
    global _client
    _client = build_client(settings)


async def close_client() -> None:
    """Close the client and release its connection pool. Called at shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("http client closed")


def get_client() -> httpx.AsyncClient:
    """Dependency returning the shared client."""
    if _client is None:
        raise RuntimeError(
            "HTTP client is not available. The application lifespan did not run - "
            "if this is a test, use TestClient as a context manager."
        )
    return _client
