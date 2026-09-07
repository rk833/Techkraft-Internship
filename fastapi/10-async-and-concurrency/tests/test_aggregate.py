"""Correctness tests for the aggregation endpoints."""

import pytest

SERVICES = ["pricing", "inventory", "reviews"]


class TestSequentialAndConcurrentAgree:
    """The two strategies must return the same data. Only the timing differs."""

    @pytest.mark.parametrize("strategy", ["sequential", "concurrent"])
    def test_all_three_services_are_present(self, client, strategy):
        body = client.get(f"/aggregate/{strategy}/HP-2200").json()
        for service in SERVICES:
            assert body[service]["sku"] == "HP-2200"

    def test_the_payloads_are_identical(self, client):
        seq = client.get("/aggregate/sequential/HP-2200").json()
        con = client.get("/aggregate/concurrent/HP-2200").json()
        for service in SERVICES:
            assert seq[service] == con[service]

    def test_gather_preserves_argument_order(self, client):
        """gather returns results positionally, not in completion order.

        Inventory is the fastest upstream and pricing the slowest, so if gather
        returned results as they arrived, pricing and inventory would be
        swapped. Worth pinning, because unpacking gather's result is where that
        assumption usually hides.
        """
        body = client.get("/aggregate/concurrent/HP-2200").json()
        assert "price" in body["pricing"]
        assert "quantity" in body["inventory"]
        assert "rating" in body["reviews"]


@pytest.mark.timing
class TestTimings:
    """Wall-clock assertions, with wide margins so they are not flaky."""

    def test_sequential_takes_at_least_the_sum(self, client):
        elapsed = client.get("/aggregate/sequential/HP-2200").json()["elapsed_ms"]
        assert elapsed >= 700

    def test_concurrent_takes_about_the_slowest(self, client):
        elapsed = client.get("/aggregate/concurrent/HP-2200").json()["elapsed_ms"]
        assert 280 <= elapsed < 600

    def test_concurrent_is_substantially_faster(self, client):
        seq = client.get("/aggregate/sequential/HP-2200").json()["elapsed_ms"]
        con = client.get("/aggregate/concurrent/HP-2200").json()["elapsed_ms"]
        assert seq / con > 1.8


class TestResilience:
    """return_exceptions=True turns all-or-nothing into best-effort."""

    def test_a_healthy_request_reports_no_failures(self, client):
        body = client.get("/aggregate/resilient/HP-2200").json()
        assert body["failed"] == []
        assert all(body[s] is not None for s in SERVICES)

    def test_one_failure_does_not_lose_the_others(self, client):
        response = client.get("/aggregate/resilient/HP-2200?break_reviews=true")
        assert response.status_code == 200
        body = response.json()
        assert body["pricing"] is not None
        assert body["inventory"] is not None
        assert body["reviews"] is None

    def test_the_failure_is_named_rather_than_hidden(self, client):
        body = client.get("/aggregate/resilient/HP-2200?break_reviews=true").json()
        assert body["failed"] == [{"service": "reviews", "error": "HTTPStatusError"}]

    @pytest.mark.timing
    def test_a_failure_does_not_slow_the_others_down(self, client):
        """A failed sibling must not stop the others completing concurrently."""
        elapsed = client.get("/aggregate/resilient/HP-2200?break_reviews=true").json()["elapsed_ms"]
        assert elapsed < 600


class TestTimeout:
    """The bound has to hold whatever the transport is."""

    @pytest.mark.timing
    def test_a_slow_upstream_becomes_a_504(self, client):
        response = client.get("/aggregate/timeout/HP-2200")
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "upstream_unavailable"

    @pytest.mark.timing
    def test_it_fails_fast_rather_than_waiting_for_the_upstream(self, client):
        """Regression guard for a measured bug.

        The upstream sleeps 4000ms and the budget is 2000ms. Before
        asyncio.timeout was added, this returned 200 after 4.2 seconds, because
        httpx's timeout is a socket timeout and ASGITransport has no socket.
        """
        import time

        start = time.perf_counter()
        response = client.get("/aggregate/timeout/HP-2200")
        elapsed = time.perf_counter() - start
        assert response.status_code == 504
        assert elapsed < 3.5, f"took {elapsed:.1f}s, the timeout is not being enforced"


class TestValidation:
    @pytest.mark.parametrize("sku", ["x", "has space", "toolong" * 10, "bad!"])
    def test_a_malformed_sku_is_422(self, client, sku):
        assert client.get(f"/aggregate/concurrent/{sku}").status_code == 422

    def test_errors_use_the_standard_envelope(self, client):
        body = client.get("/aggregate/concurrent/x").json()
        assert set(body["error"]) == {"code", "message", "details", "reference"}


class TestClientLifecycle:
    def test_the_client_is_unavailable_without_lifespan(self):
        """The failure names its own cause.

        Forgetting the context manager is the single easiest mistake to make
        here, so get_client raises a message that says what to do rather than
        an AttributeError on None.
        """
        from clients import _client, get_client

        assert _client is None
        with pytest.raises(RuntimeError, match="lifespan did not run"):
            get_client()

    def test_the_client_exists_inside_lifespan(self, client):
        import clients

        assert clients._client is not None
