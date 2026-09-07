"""Concurrency tests.

These are the tests that prove the module's claims. They need overlapping
requests, so they use the async client - TestClient is synchronous and cannot
issue two requests at once, which would make every one of these pass for the
wrong reason.

Margins are wide. The assertions distinguish "overlapped" from "serialised",
which are an order of magnitude apart, not two timings that are close.
"""

import asyncio
import time

import pytest

pytestmark = pytest.mark.timing

WORK_MS = 150
N = 8


async def fire(aclient, path: str, n: int = N) -> float:
    """Issue n concurrent requests, return total wall time in ms."""
    start = time.perf_counter()
    responses = await asyncio.gather(*(aclient.get(path) for _ in range(n)))
    assert all(r.status_code == 200 for r in responses)
    return (time.perf_counter() - start) * 1000


class TestOverlapping:
    """Three of the four variants overlap. One does not."""

    async def test_async_with_await_overlaps(self, aclient):
        total = await fire(aclient, f"/blocking/async-correct?ms={WORK_MS}")
        assert total < WORK_MS * 3, f"{total:.0f}ms for {N} requests of {WORK_MS}ms"

    async def test_sync_def_overlaps_via_the_threadpool(self, aclient):
        """A plain def endpoint is not the slow option.

        FastAPI runs it in a worker thread, so blocking there blocks that
        thread rather than the event loop.
        """
        total = await fire(aclient, f"/blocking/sync?ms={WORK_MS}")
        assert total < WORK_MS * 3, f"{total:.0f}ms for {N} requests of {WORK_MS}ms"

    async def test_run_in_threadpool_overlaps(self, aclient):
        total = await fire(aclient, f"/blocking/threadpool?ms={WORK_MS}")
        assert total < WORK_MS * 3, f"{total:.0f}ms for {N} requests of {WORK_MS}ms"

    async def test_async_with_a_blocking_call_serialises(self, aclient):
        """The trap, asserted rather than described.

        time.sleep inside async def holds the event loop, so the requests run
        one after another. The result is roughly N times a single request.
        """
        total = await fire(aclient, f"/blocking/async-blocking?ms={WORK_MS}")
        assert total > WORK_MS * (N - 2), (
            f"{total:.0f}ms for {N} requests of {WORK_MS}ms - expected serialisation"
        )


class TestTheLoopStaysFree:
    """The consequence that actually matters: can the server serve anyone else?

    Measuring this in-process needs care. The obvious approach - start the slow
    request, sleep briefly, then time a /health call - does not work here,
    because the test shares the event loop it is trying to observe. The brief
    sleep is itself blocked, so the health call is timed only after the
    blocking work has already finished, and every variant looks fast.

    Taking the start timestamp before anything is scheduled, and recording when
    each request *completes*, avoids depending on the loop the measurement is
    about.
    """

    async def probe(self, aclient, path: str) -> float:
        """Return when /health completed, relative to a shared start."""
        start = time.perf_counter()

        async def run(target: str) -> tuple[str, float]:
            await aclient.get(target)
            return target, (time.perf_counter() - start) * 1000

        finished = dict(await asyncio.gather(run(path), run("/health")))
        return finished["/health"]

    async def test_health_is_fast_during_a_properly_awaited_request(self, aclient):
        latency = await self.probe(aclient, "/blocking/async-correct?ms=800")
        assert latency < 200, f"health took {latency:.0f}ms"

    async def test_health_is_fast_during_a_sync_endpoint(self, aclient):
        latency = await self.probe(aclient, "/blocking/sync?ms=800")
        assert latency < 200, f"health took {latency:.0f}ms"

    async def test_health_is_blocked_by_a_blocking_async_endpoint(self, aclient):
        """One bad endpoint takes the whole server down for its duration.

        /health does nothing and touches nothing that endpoint touches. It is
        slow purely because the event loop is not free to run it.
        """
        latency = await self.probe(aclient, "/blocking/async-blocking?ms=800")
        assert latency > 500, f"health took only {latency:.0f}ms - expected blocking"


class TestThreadpoolCapacity:
    """The threadpool is finite, so def endpoints have a ceiling too."""

    async def test_the_limiter_is_reported(self, aclient):
        body = (await aclient.get("/blocking/threadpool-size")).json()
        assert body["total_tokens"] > 0

    async def test_requests_beyond_the_pool_size_queue(self, aclient):
        """Above the pool size, requests wait for a free thread.

        A much higher ceiling than blocking the loop, but still a ceiling - and
        the reason a slow sync endpoint is not free of consequences.
        """
        body = (await aclient.get("/blocking/threadpool-size")).json()
        capacity = body["total_tokens"]
        within = await fire(aclient, "/blocking/sync?ms=100", n=min(capacity, 20))
        beyond = await fire(aclient, "/blocking/sync?ms=100", n=capacity * 2 + 10)
        assert beyond > within * 1.5, f"within={within:.0f}ms beyond={beyond:.0f}ms"


class TestCpuBoundWork:
    """Threads do not parallelise Python bytecode."""

    async def test_cpu_work_does_not_overlap_even_in_the_threadpool(self, aclient):
        """The GIL serialises it, so offloading buys almost nothing.

        This is the limit of run_in_threadpool, and the reason CPU-bound work
        needs a process pool or a separate service rather than a thread.
        """
        rounds = 200_000
        start = time.perf_counter()
        await aclient.get(f"/blocking/cpu-sync?rounds={rounds}")
        single = (time.perf_counter() - start) * 1000

        total = await fire(aclient, f"/blocking/cpu-sync?rounds={rounds}", n=6)
        assert total > single * 3, (
            f"single={single:.0f}ms, 6 concurrent={total:.0f}ms - "
            "expected near-serial behaviour from the GIL"
        )


class TestGatherSemantics:
    """asyncio.gather behaviour that the aggregator depends on."""

    async def test_gather_is_bounded_by_the_slowest_member(self, aclient):
        start = time.perf_counter()
        await asyncio.gather(
            aclient.get("/blocking/async-correct?ms=100"),
            aclient.get("/blocking/async-correct?ms=200"),
            aclient.get("/blocking/async-correct?ms=300"),
        )
        total = (time.perf_counter() - start) * 1000
        assert 280 < total < 700, f"{total:.0f}ms - expected about the slowest, 300ms"
