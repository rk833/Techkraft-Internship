"""Aggregation routes."""

import asyncio
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Path, Query

from clients import get_client
from config import Settings, get_settings
from errors import UpstreamTimeoutError
from schemas import ERROR_RESPONSES
from services import aggregate_concurrent, aggregate_resilient, aggregate_sequential

router = APIRouter(prefix="/aggregate", tags=["aggregate"], responses=ERROR_RESPONSES)

Client = Annotated[httpx.AsyncClient, Depends(get_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Sku = Annotated[str, Path(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9-]+$")]


@router.get("/sequential/{sku}", summary="Three upstream calls, one after another")
async def sequential(sku: Sku, client: Client) -> dict:
    """Total time is the sum of the three delays."""
    return await aggregate_sequential(client, sku)


@router.get("/concurrent/{sku}", summary="Three upstream calls at once")
async def concurrent(sku: Sku, client: Client) -> dict:
    """Total time is the slowest of the three delays."""
    return await aggregate_concurrent(client, sku)


@router.get("/resilient/{sku}", summary="Concurrent, tolerating failures")
async def resilient(
    sku: Sku,
    client: Client,
    break_reviews: Annotated[bool, Query(description="Make the reviews call fail")] = False,
) -> dict:
    """Return whatever succeeded, naming what did not.

    The break_reviews flag points the reviews call at a path that does not
    exist upstream, which produces a real 404 and a real raise_for_status
    failure rather than a simulated one.
    """
    return await aggregate_resilient(client, sku, break_reviews=break_reviews)


@router.get("/timeout/{sku}", summary="A call that exceeds the timeout")
async def timeout(sku: Sku, client: Client, settings: SettingsDep) -> dict:
    """Ask the upstream for a delay longer than the configured timeout.

    Two layers of timeout, deliberately.

    httpx's own timeout is the normal one and is enough over real HTTP. It is
    not enough here: with ASGITransport there is no socket, so httpx has
    nothing to time out on and the call runs to completion. Measured before
    this guard was added, a 4000ms upstream call returned 200 after 4.2s
    despite a 2.0s client timeout.

    asyncio.timeout wraps the await itself, so the bound holds whatever the
    transport is. It is cheap, and it converts a whole class of "the request
    hung" incident into a fast, explicit failure.
    """
    budget = settings.upstream_timeout_seconds
    try:
        async with asyncio.timeout(budget):
            response = await client.get(f"/pricing/{sku}", params={"delay_ms": 4000})
            return response.json()
    except (TimeoutError, httpx.TimeoutException) as exc:
        # 504 rather than 503: the upstream is reachable, it was simply too slow.
        raise UpstreamTimeoutError(
            f"The pricing service did not respond within {budget:.1f}s"
        ) from exc
