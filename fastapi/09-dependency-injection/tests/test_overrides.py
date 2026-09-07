"""dependency_overrides.

The payoff for routing everything through Depends(). Each test here replaces a
real dependency with a fake, without touching a single line of production code
and without patching an import.
"""

import pytest

from config import Settings, get_settings
from dependencies import PaginationParams, get_store, get_task_or_404, verify_api_key
from main import app
from tests.conftest import FakeStore


class TestOverrideTheStore:
    """Swap the data layer for a fake."""

    def test_endpoints_read_from_the_injected_store(self, client, fake_store):
        app.dependency_overrides[get_store] = lambda: fake_store
        body = client.get("/tasks").json()
        assert body["total"] == 2
        assert [t["title"] for t in body["items"]] == ["Fake task one", "Fake task two"]

    def test_the_fake_is_not_a_subclass(self, fake_store):
        """The seam is duck-typed, not an inheritance hook.

        FakeStore implements three methods and nothing else. If the override
        required a TaskStore subclass, this fake would not work and the seam
        would be far less useful.
        """
        from store import TaskStore

        assert not isinstance(fake_store, TaskStore)

    def test_the_sub_dependency_uses_the_override_too(self, client, fake_store):
        """get_task_or_404 depends on get_store, so overriding the parent is enough.

        This is the property that makes overrides scale: replacing one node
        replaces it everywhere in the graph, at any depth.
        """
        app.dependency_overrides[get_store] = lambda: fake_store
        assert client.get("/tasks/101").json()["title"] == "Fake task one"
        assert client.get("/tasks/1").status_code == 404

    def test_an_empty_store_is_easy_to_arrange(self, client):
        app.dependency_overrides[get_store] = lambda: FakeStore(tasks=[])
        assert client.get("/tasks").json()["total"] == 0


class TestOverrideTheGuard:
    """Turn authentication off for tests that are not about authentication."""

    def test_admin_routes_open_up(self, client):
        assert client.get("/admin/tasks").status_code == 401
        app.dependency_overrides[verify_api_key] = lambda: None
        assert client.get("/admin/tasks").status_code == 200

    def test_this_is_why_the_guard_returns_nothing(self, client):
        """A no-op lambda is a complete replacement for a side-effect dependency.

        Every admin test that is really about admin behaviour can use this
        instead of threading a real key through, which is what makes module 12
        tractable.
        """
        app.dependency_overrides[verify_api_key] = lambda: None
        assert client.get("/admin/stats").json()["total"] == 4


class TestOverrideSettings:
    """Change configuration for one test without touching the environment."""

    def test_a_different_environment_can_be_injected(self, client):
        app.dependency_overrides[get_settings] = lambda: Settings(
            environment="staging", app_name="Injected App"
        )
        body = client.get("/diagnostics/context").json()
        assert body["environment"] == "staging"
        assert body["app_name"] == "Injected App"

    def test_the_real_settings_come_back_afterwards(self, client):
        """Proves the autouse fixture actually clears overrides.

        Without that clearing, the previous test would leak and this one would
        fail - but it would fail here rather than there, which is the confusing
        part.
        """
        assert client.get("/diagnostics/context").json()["environment"] == "development"

    def test_overriding_settings_beats_clearing_the_lru_cache(self, client):
        """get_settings is lru_cached, and the override bypasses the cache entirely.

        Reaching for get_settings.cache_clear() instead would mutate global
        process state and affect every other test in the session.
        """
        app.dependency_overrides[get_settings] = lambda: Settings(environment="production")
        assert client.get("/diagnostics/context").json()["environment"] == "production"
        assert get_settings().environment == "development"


class TestOverrideAClassDependency:
    """A class dependency is overridden the same way a function is."""

    def test_pagination_can_be_forced(self, client):
        app.dependency_overrides[PaginationParams] = lambda: PaginationParams(limit=1, offset=3)
        body = client.get("/tasks").json()
        assert body["limit"] == 1
        assert body["count"] == 1
        assert body["offset"] == 3

    def test_the_override_applies_to_every_paginated_endpoint(self, client):
        app.dependency_overrides[PaginationParams] = lambda: PaginationParams(limit=1, offset=0)
        app.dependency_overrides[verify_api_key] = lambda: None
        for path in ("/tasks", "/tasks/search?q=re", "/admin/tasks"):
            assert client.get(path).json()["limit"] == 1, path


class TestOverrideASubDependencyDirectly:
    """Replace a node in the middle of the graph."""

    def test_get_task_or_404_can_be_replaced_wholesale(self, client):
        sentinel = {
            "id": 999, "title": "Injected task", "description": None,
            "status": "todo", "priority": "medium", "tags": [],
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        }
        app.dependency_overrides[get_task_or_404] = lambda: sentinel
        body = client.get("/tasks/12345").json()
        assert body["title"] == "Injected task"


class TestOverrideHygiene:
    """The failure mode nobody warns you about."""

    def test_overrides_are_empty_at_the_start_of_every_test(self):
        assert app.dependency_overrides == {}

    @pytest.mark.parametrize("run", [1, 2, 3])
    def test_setting_an_override_does_not_leak_between_parametrized_runs(self, client, run):
        assert app.dependency_overrides == {}
        app.dependency_overrides[get_store] = lambda: FakeStore()
        assert client.get("/tasks").json()["total"] == 2
