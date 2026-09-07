"""Happy-path CRUD tests.

One test per behaviour, named so a failure report reads as a sentence about
what broke rather than as a test number.
"""

import pytest

from schemas import Priority, TaskStatus


class TestCreate:
    """POST /tasks"""

    def test_returns_201_and_the_created_task(self, client):
        response = client.post("/tasks", json={"title": "Buy milk"})
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "Buy milk"
        assert body["id"] > 0

    def test_new_task_always_starts_as_todo(self, client):
        """Status is not on TaskCreate, so a client cannot open a task as done."""
        response = client.post("/tasks", json={"title": "Starts as todo"})
        assert response.json()["status"] == TaskStatus.TODO

    def test_defaults_are_applied(self, client):
        body = client.post("/tasks", json={"title": "Minimal task"}).json()
        assert body["priority"] == Priority.MEDIUM
        assert body["description"] is None
        assert body["tags"] == []

    def test_created_task_is_retrievable(self, client):
        created = client.post("/tasks", json={"title": "Round trip"}).json()
        fetched = client.get(f"/tasks/{created['id']}").json()
        assert fetched == created

    def test_timestamps_are_set(self, client):
        body = client.post("/tasks", json={"title": "Timestamped"}).json()
        assert body["created_at"] == body["updated_at"]


class TestList:
    """GET /tasks"""

    def test_returns_the_seeded_tasks(self, client):
        body = client.get("/tasks").json()
        assert body["total"] == 4
        assert body["count"] == 4

    def test_filters_by_status(self, client):
        body = client.get("/tasks?status=todo").json()
        assert body["total"] == 2
        assert {t["status"] for t in body["items"]} == {"todo"}

    def test_filters_by_priority(self, client):
        body = client.get("/tasks?priority=high").json()
        assert {t["priority"] for t in body["items"]} == {"high"}

    def test_filters_by_search_term(self, client):
        body = client.get("/tasks?q=renew").json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Renew domain"

    def test_filters_combine(self, client):
        body = client.get("/tasks?status=todo&priority=low").json()
        assert body["total"] == 1

    def test_total_is_the_count_before_paging(self, client):
        body = client.get("/tasks?limit=2").json()
        assert body["total"] == 4
        assert body["count"] == 2

    def test_offset_past_the_end_is_an_empty_page_not_an_error(self, client):
        response = client.get("/tasks?offset=999")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_pages_do_not_overlap(self, client):
        first = client.get("/tasks?limit=2&offset=0").json()["items"]
        second = client.get("/tasks?limit=2&offset=2").json()["items"]
        assert {t["id"] for t in first}.isdisjoint({t["id"] for t in second})


class TestGet:
    """GET /tasks/{id}"""

    def test_returns_the_task(self, client):
        body = client.get("/tasks/1").json()
        assert body["id"] == 1
        assert body["title"] == "Write the module 08 README"


class TestReplace:
    """PUT /tasks/{id}"""

    def test_replaces_every_field(self, client):
        response = client.put("/tasks/1", json={"title": "Completely new", "status": "done"})
        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Completely new"
        assert body["status"] == "done"

    def test_omitted_fields_revert_to_defaults(self, client):
        before = client.get("/tasks/1").json()
        assert before["tags"] == ["docs", "fastapi"]
        after = client.put("/tasks/1", json={"title": "Replaced"}).json()
        assert after["tags"] == []
        assert after["priority"] == Priority.MEDIUM
        assert after["description"] is None

    def test_preserves_id_and_created_at(self, client):
        before = client.get("/tasks/1").json()
        after = client.put("/tasks/1", json={"title": "Replaced"}).json()
        assert after["id"] == before["id"]
        assert after["created_at"] == before["created_at"]

    def test_is_idempotent(self, client):
        """Sending the same PUT twice leaves the same state.

        This is the property that distinguishes PUT from POST, and it is worth
        an explicit test because it is easy to break by generating something
        new inside the handler.
        """
        payload = {"title": "Idempotent", "priority": "high", "status": "done", "tags": ["x"]}
        first = client.put("/tasks/2", json=payload).json()
        second = client.put("/tasks/2", json=payload).json()
        first.pop("updated_at")
        second.pop("updated_at")
        assert first == second


class TestUpdate:
    """PATCH /tasks/{id}"""

    def test_changes_only_the_field_sent(self, client):
        before = client.get("/tasks/1").json()
        after = client.patch("/tasks/1", json={"priority": "low"}).json()
        assert after["priority"] == "low"
        assert after["title"] == before["title"]
        assert after["tags"] == before["tags"]
        assert after["description"] == before["description"]

    def test_empty_patch_is_a_no_op(self, client):
        before = client.get("/tasks/1").json()
        after = client.patch("/tasks/1", json={}).json()
        before.pop("updated_at")
        after.pop("updated_at")
        assert before == after

    @pytest.mark.parametrize(
        "field,value",
        [
            ("title", "Renamed"),
            ("description", "New description"),
            ("priority", "high"),
            ("status", "in_progress"),
            ("tags", ["a", "b"]),
        ],
    )
    def test_each_field_can_be_patched(self, client, field, value):
        """parametrize runs this once per row, reported as five separate tests.

        A loop inside one test would stop at the first failure and report one
        name; this reports exactly which field broke.
        """
        body = client.patch("/tasks/2", json={field: value}).json()
        assert body[field] == value


class TestComplete:
    """POST /tasks/{id}/complete"""

    def test_marks_the_task_done(self, client):
        body = client.post("/tasks/2/complete").json()
        assert body["status"] == "done"

    def test_the_change_persists(self, client):
        client.post("/tasks/2/complete")
        assert client.get("/tasks/2").json()["status"] == "done"


class TestDelete:
    """DELETE /tasks/{id}"""

    def test_returns_204_with_no_body(self, client):
        response = client.delete("/tasks/3")
        assert response.status_code == 204
        assert response.text == ""

    def test_the_task_is_gone_afterwards(self, client):
        client.delete("/tasks/3")
        assert client.get("/tasks/3").status_code == 404

    def test_other_tasks_are_untouched(self, client):
        client.delete("/tasks/3")
        assert client.get("/tasks").json()["total"] == 3


class TestIsolation:
    """These two only both pass because of the autouse reset fixture.

    Written as a deliberate trap: each mutates the store and then asserts a
    count that is only correct from a clean start.
    """

    def test_a_creates_a_task(self, client):
        client.post("/tasks", json={"title": "Created by test a"})
        assert client.get("/tasks").json()["total"] == 5

    def test_b_also_expects_four_seeded_tasks(self, client):
        assert client.get("/tasks").json()["total"] == 4
