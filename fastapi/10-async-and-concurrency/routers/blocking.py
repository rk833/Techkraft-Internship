"""The same work, written four ways.

Each endpoint waits 200ms by default. They differ only in how, and that
difference decides whether the server can serve anyone else meanwhile.

Fire ten concurrent requests at each and the wall-clock totals separate them
completely. That measurement is the whole point of the module.
"""

import asyncio
import hashlib
import logging
import time
from typing import Annotated

import anyio
from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger("api.blocking")

router = APIRouter(prefix="/blocking", tags=["blocking"])

Ms = Annotated[int, Query(ge=0, le=5000, description="How long to wait")]


def slow_io(ms: int) -> str:
    """Blocking I/O. Stands in for a sync database driver or requests.get."""
    time.sleep(ms / 1000)
    return f"slept {ms}ms"


def slow_cpu(rounds: int) -> str:
    """CPU-bound work, standing in for password hashing.

    Not an arbitrary example: module 12 hashes passwords with bcrypt, which is
    deliberately expensive and behaves exactly like this.
    """
    digest = hashlib.pbkdf2_hmac("sha256", b"password", b"salt", rounds)
    return digest.hex()[:16]


@router.get("/sync", summary="def endpoint doing blocking work - correct")
def sync_endpoint(ms: Ms = 200) -> dict:
    """A plain `def` endpoint.

    FastAPI runs it in a worker thread, so blocking here blocks that thread and
    not the event loop. Ten concurrent requests overlap.

    This is why `def` is not the slow option. For blocking code it is the
    correct one, and writing `async def` around the same body would be worse.
    """
    return {"variant": "sync (threadpool)", "result": slow_io(ms)}


@router.get("/async-blocking", summary="async def doing blocking work - the trap")
async def async_blocking_endpoint(ms: Ms = 200) -> dict:
    """An `async def` endpoint containing a blocking call.

    time.sleep does not yield to the event loop. For its whole duration this
    coroutine holds the loop, so no other request is served - not this endpoint,
    not any other endpoint, not the health check.

    Nothing warns about this. It passes review, it passes a single-request test,
    and it fails only under concurrency.
    """
    return {"variant": "async + time.sleep (BLOCKS the loop)", "result": slow_io(ms)}


@router.get("/async-correct", summary="async def awaiting properly")
async def async_correct_endpoint(ms: Ms = 200) -> dict:
    """The same wait, awaited.

    asyncio.sleep yields control back to the loop, so ten concurrent requests
    take about as long as one.
    """
    await asyncio.sleep(ms / 1000)
    return {"variant": "async + asyncio.sleep", "result": f"awaited {ms}ms"}


@router.get("/threadpool", summary="async def offloading blocking work")
async def threadpool_endpoint(ms: Ms = 200) -> dict:
    """An `async def` endpoint that has to call blocking code.

    run_in_threadpool moves it off the loop, restoring the behaviour a plain
    `def` endpoint would have had. This is the escape hatch for when an endpoint
    must be `async` - because it also awaits something - but has one stubborn
    synchronous dependency.
    """
    result = await run_in_threadpool(slow_io, ms)
    return {"variant": "async + run_in_threadpool", "result": result}


@router.get("/cpu-sync", summary="def endpoint doing CPU-bound work")
def cpu_sync(rounds: Annotated[int, Query(ge=1, le=2_000_000)] = 300_000) -> dict:
    """CPU-bound work in the threadpool.

    Threads do not give CPU-bound Python work true parallelism, because the GIL
    only lets one thread execute bytecode at a time. Offloading helps I/O far
    more than it helps computation, and this endpoint exists so that claim can
    be measured rather than asserted.
    """
    return {"variant": "sync CPU (threadpool)", "digest": slow_cpu(rounds)}


@router.get("/cpu-async", summary="async def doing CPU-bound work")
async def cpu_async(rounds: Annotated[int, Query(ge=1, le=2_000_000)] = 300_000) -> dict:
    """The same computation on the event loop. Blocks everything."""
    return {"variant": "async CPU (BLOCKS the loop)", "digest": slow_cpu(rounds)}


@router.get("/threadpool-size", summary="Report the threadpool capacity")
async def threadpool_size() -> dict:
    """Show how many worker threads sync endpoints share.

    The limit is finite. Beyond it, requests queue - so a `def` endpoint that
    blocks for a long time is still a scalability ceiling, just a much higher
    one than blocking the event loop.
    """
    limiter = anyio.to_thread.current_default_thread_limiter()
    return {
        "total_tokens": limiter.total_tokens,
        "borrowed_tokens": limiter.borrowed_tokens,
        "available": limiter.total_tokens - limiter.borrowed_tokens,
    }
