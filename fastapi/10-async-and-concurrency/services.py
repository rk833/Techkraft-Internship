"""The aggregation logic.

Three ways of fetching the same three things, so the difference between them can
be measured rather than argued about.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("api.services")


async def fetch(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    """Fetch one upstream resource.

    Awaiting the response is the only thing that makes concurrency possible.
    While this coroutine waits, the event loop is free to run others - which is
    the entire mechanism behind everything else in this module.
    """
    response = await client.get(path)
    response.raise_for_status()
    return response.json()


async def aggregate_sequential(client: httpx.AsyncClient, sku: str) -> dict[str, Any]:
    """Fetch all three, one after another.

    Every call is awaited before the next one starts, so the total is the sum of
    the three delays. This is correct, idiomatic-looking async code, and it is
    exactly as slow as blocking code would be. `async` on its own buys nothing;
    overlapping the waits is what buys something.
    """
    start = time.perf_counter()
    pricing = await fetch(client, f"/pricing/{sku}")
    inventory = await fetch(client, f"/inventory/{sku}")
    reviews = await fetch(client, f"/reviews/{sku}")
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "sku": sku,
        "strategy": "sequential",
        "elapsed_ms": round(elapsed_ms, 1),
        "pricing": pricing,
        "inventory": inventory,
        "reviews": reviews,
    }


async def aggregate_concurrent(client: httpx.AsyncClient, sku: str) -> dict[str, Any]:
    """Fetch all three at once.

    gather schedules all three coroutines and waits for all of them, so the
    total is the slowest one rather than the sum. The three calls do not depend
    on each other, which is the precondition - gather cannot help when the
    second request needs the first one's answer.
    """
    start = time.perf_counter()
    pricing, inventory, reviews = await asyncio.gather(
        fetch(client, f"/pricing/{sku}"),
        fetch(client, f"/inventory/{sku}"),
        fetch(client, f"/reviews/{sku}"),
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {
        "sku": sku,
        "strategy": "concurrent",
        "elapsed_ms": round(elapsed_ms, 1),
        "pricing": pricing,
        "inventory": inventory,
        "reviews": reviews,
    }


async def aggregate_resilient(
    client: httpx.AsyncClient, sku: str, break_reviews: bool = False
) -> dict[str, Any]:
    """Fetch all three at once, tolerating individual failures.

    return_exceptions=True changes gather from all-or-nothing into best-effort:
    a failing call yields its exception instead of cancelling the others. Which
    behaviour is wanted is a product decision, not a technical one - a price is
    probably essential, a review count probably is not.

    Without it, one failed call cancels the siblings and the whole endpoint
    fails, which is rarely what a page assembling several panels wants.

    break_reviews points the reviews call at a path the upstream does not serve,
    producing a genuine 404 and a genuine raise_for_status failure. Passing it
    as an argument rather than patching the module keeps the failure injection
    local to one call instead of global to the process.
    """
    start = time.perf_counter()
    names = ["pricing", "inventory", "reviews"]
    reviews_path = "/does-not-exist" if break_reviews else f"/reviews/{sku}"
    results = await asyncio.gather(
        fetch(client, f"/pricing/{sku}"),
        fetch(client, f"/inventory/{sku}"),
        fetch(client, reviews_path),
        return_exceptions=True,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    payload: dict[str, Any] = {
        "sku": sku,
        "strategy": "resilient",
        "elapsed_ms": round(elapsed_ms, 1),
        "failed": [],
    }
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            logger.warning("upstream %s failed: %s", name, type(result).__name__)
            payload[name] = None
            payload["failed"].append({"service": name, "error": type(result).__name__})
        else:
            payload[name] = result
    return payload
