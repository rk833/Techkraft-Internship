"""Tests for the dependency mechanics themselves."""

import pytest

import dependencies as deps

PAGINATED_ENDPOINTS = [
    "/tasks",
    # q has min_length=2, so a single character is a 422 for an unrelated reason
    "/tasks/search?q=re",
    "/tasks/tagged/fastapi",
    "/admin/tasks",
]


class TestPaginationDependency:
    """One class dependency, four endpoints, two of them in different routers."""

    @pytest.mark.parametrize("path", PAGINATED_ENDPOINTS)
    def test_every_paginated_endpoint_returns_the_same_envelope(self, client, admin_headers, path):
        body = client.get(path, headers=admin_headers).json()
        assert set(body) == {"total", "count", "limit", "offset", "items"}

    @pytest.mark.parametrize("path", PAGINATED_ENDPOINTS)
    def test_defaults_are_identical_everywhere(self, client, admin_headers, path):
        body = client.get(path, headers=admin_headers).json()
        assert body["limit"] == 20
        assert body["offset"] == 0

    @pytest.mark.parametrize("path", PAGINATED_ENDPOINTS)
    @pytest.mark.parametrize("query", ["limit=0", "limit=500", "offset=-1", "limit=abc"])
    def test_validation_applies_everywhere(self, client, admin_headers, path, query):
        """The constraints live on PaginationParams.__init__, not on any endpoint.

        Sixteen assertions from one declaration. Adding a fifth paginated
        endpoint inherits all of it.
        """
        joiner = "&" if "?" in path else "?"
        response = client.get(f"{path}{joiner}{query}", headers=admin_headers)
        assert response.status_code == 422

    def test_resolved_values_reach_the_endpoint(self, client):
        body = client.get("/diagnostics/pagination?limit=5&offset=10").json()
        assert body == {"limit": 5, "offset": 10, "repr": "PaginationParams(limit=5, offset=10)"}

    def test_total_is_computed_before_slicing(self, client):
        body = client.get("/tasks?limit=2").json()
        assert body["total"] == 4
        assert body["count"] == 2

    def test_pages_do_not_overlap(self, client):
        first = client.get("/tasks?limit=2&offset=0").json()["items"]
        second = client.get("/tasks?limit=2&offset=2").json()["items"]
        assert {t["id"] for t in first}.isdisjoint({t["id"] for t in second})


class TestSubDependency:
    """get_task_or_404 depends on get_store and consumes the path parameter."""

    def test_resolves_an_existing_task(self, client):
        assert client.get("/tasks/1").json()["id"] == 1

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/tasks/999"),
            ("put", "/tasks/999"),
            ("patch", "/tasks/999"),
            ("delete", "/tasks/999"),
            ("post", "/tasks/999/complete"),
        ],
    )
    def test_the_404_is_raised_before_any_handler_runs(self, client, method, path):
        payload = {"title": "Irrelevant"} if method in ("put", "patch") else None
        response = client.request(method.upper(), path, json=payload)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "No task with id 999"


class TestDependencyCaching:
    """A dependency reached twice in the graph is executed once."""

    def test_a_shared_subdependency_runs_once_per_request(self, client):
        body = client.get("/diagnostics/cache").json()
        assert body["shared_calls"] == 1

    def test_use_cache_false_forces_a_second_call(self, client):
        body = client.get("/diagnostics/cache-off").json()
        assert body["shared_calls"] == 2

    def test_the_cache_does_not_survive_between_requests(self, client):
        assert client.get("/diagnostics/cache").json()["shared_calls"] == 1
        assert client.get("/diagnostics/cache").json()["shared_calls"] == 1


class TestYieldTeardown:
    """Teardown runs, and it runs in reverse order of setup."""

    def test_nested_dependencies_tear_down_last_in_first_out(self, client):
        client.get("/diagnostics/nested")
        assert deps.EVENTS == [
            "outer.setup",
            "inner.setup",
            "inner.teardown",
            "outer.teardown",
        ]

    def test_teardown_has_not_run_when_the_endpoint_body_executes(self, client):
        body = client.get("/diagnostics/nested").json()
        assert body["events_so_far"] == ["outer.setup", "inner.setup"]

    def test_commit_on_success(self, client):
        client.get("/diagnostics/unit-of-work")
        assert deps.EVENTS == ["uow.begin", "uow.commit", "uow.close"]

    def test_rollback_on_an_unhandled_exception(self, raw_client):
        response = raw_client.get("/diagnostics/unit-of-work/fail")
        assert response.status_code == 500
        assert deps.EVENTS == ["uow.begin", "uow.rollback", "uow.close"]

    def test_rollback_on_a_deliberately_raised_http_error(self, client):
        """A 404 raised inside the endpoint still rolls back.

        This is the case that decides whether a request that fails halfway
        leaves a half-finished write committed. It is not obvious from reading
        the code either way, so it gets an explicit test.
        """
        response = client.get("/diagnostics/unit-of-work/http-error")
        assert response.status_code == 404
        assert deps.EVENTS == ["uow.begin", "uow.rollback", "uow.close"]

    def test_close_always_runs(self, raw_client):
        for path in ("/diagnostics/unit-of-work", "/diagnostics/unit-of-work/fail",
                     "/diagnostics/unit-of-work/http-error"):
            deps.EVENTS.clear()
            raw_client.get(path)
            assert deps.EVENTS[-1] == "uow.close", path


class TestDependencyResolutionOrder:
    """Declaration order decides which failures open a transaction."""

    def test_a_404_from_an_earlier_dependency_never_opens_the_unit_of_work(self, client):
        """get_task_or_404 is declared before uow, so it raises first.

        A request that cannot proceed never starts a transaction. That is a
        real benefit of parameter ordering, and it would silently reverse if
        the parameters were reordered.
        """
        client.patch("/tasks/999", json={"priority": "low"})
        assert deps.EVENTS == []

    def test_a_body_validation_failure_does_open_and_roll_back(self, client):
        """Body validation happens after dependencies are solved.

        So an invalid body opens a transaction that was never going to be used.
        Harmless because it rolls back, and worth knowing before profiling a
        database under a client sending malformed payloads.
        """
        response = client.patch("/tasks/1", json={"priority": "urgent"})
        assert response.status_code == 422
        assert deps.EVENTS == ["uow.begin", "uow.rollback", "uow.close"]

    def test_a_conflict_rolls_back(self, client):
        response = client.post("/tasks/4/complete")
        assert response.status_code == 409
        assert deps.EVENTS == ["uow.begin", "uow.rollback", "uow.close"]


class TestApplicationLevelDependency:
    """record_request is registered on the app, so it runs for every route."""

    def test_it_runs_for_every_request(self, client):
        assert client.get("/diagnostics/context").json()["audited_by_app_dependency"] is True


class TestRouterLevelGuard:
    """verify_api_key is declared once on the admin router."""

    @pytest.mark.parametrize("path", ["/admin/tasks", "/admin/stats"])
    def test_no_key_is_rejected(self, client, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ["/admin/tasks", "/admin/stats"])
    def test_a_wrong_key_is_rejected(self, client, path):
        assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401

    @pytest.mark.parametrize("path", ["/admin/tasks", "/admin/stats"])
    def test_the_correct_key_is_accepted(self, client, admin_headers, path):
        assert client.get(path, headers=admin_headers).status_code == 200

    def test_non_admin_routes_are_unaffected(self, client):
        assert client.get("/tasks").status_code == 200

    def test_the_401_uses_the_standard_error_envelope(self, client):
        body = client.get("/admin/tasks").json()
        assert set(body["error"]) == {"code", "message", "details", "reference"}

    def test_the_guard_is_documented_on_every_admin_route(self, client):
        schema = client.get("/openapi.json").json()
        admin_paths = [p for p in schema["paths"] if p.startswith("/admin")]
        assert admin_paths
        for path in admin_paths:
            for operation in schema["paths"][path].values():
                assert "401" in operation["responses"], path
