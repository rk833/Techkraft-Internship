"""A stand-in for three slow external services.

A separate ASGI application, not a set of routes on the main app. That matters:
the aggregator reaches it through a real httpx client over a real ASGI
transport, so the concurrency being measured is genuine rather than three
asyncio.sleep calls dressed up as network calls.

In development it can also be run as its own uvicorn process and reached over
real HTTP by setting UPSTREAM_BASE_URL.
"""

import asyncio

from fastapi import FastAPI, Query

app = FastAPI(title="Slow Upstream Services", version="0.1.0")

# Each service is slow in a different way, so the sequential total is obviously
# the sum and the concurrent total is obviously the maximum.
DEFAULT_DELAYS_MS = {"pricing": 300, "inventory": 200, "reviews": 250}


async def _delay(ms: int) -> None:
    """Sleep without blocking the event loop."""
    await asyncio.sleep(ms / 1000)


@app.get("/pricing/{sku}")
async def pricing(sku: str, delay_ms: int = Query(default=DEFAULT_DELAYS_MS["pricing"], ge=0, le=5000)):
    """Return a price after a delay."""
    await _delay(delay_ms)
    return {"sku": sku, "price": 249.00, "currency": "GBP", "delay_ms": delay_ms}


@app.get("/inventory/{sku}")
async def inventory(sku: str, delay_ms: int = Query(default=DEFAULT_DELAYS_MS["inventory"], ge=0, le=5000)):
    """Return stock levels after a delay."""
    await _delay(delay_ms)
    return {"sku": sku, "in_stock": True, "quantity": 42, "delay_ms": delay_ms}


@app.get("/reviews/{sku}")
async def reviews(sku: str, delay_ms: int = Query(default=DEFAULT_DELAYS_MS["reviews"], ge=0, le=5000)):
    """Return review data after a delay."""
    await _delay(delay_ms)
    return {"sku": sku, "rating": 4.6, "count": 118, "delay_ms": delay_ms}


@app.get("/flaky/{sku}")
async def flaky(sku: str, fail: bool = False, delay_ms: int = Query(default=100, ge=0, le=5000)):
    """A service that can be told to fail, for testing partial results."""
    await _delay(delay_ms)
    if fail:
        return {"detail": "upstream exploded"}, 500
    return {"sku": sku, "ok": True}


@app.get("/health")
async def health():
    """Health check for the upstream itself."""
    return {"status": "ok"}
