"""Failure-path tests.

Every endpoint has at least one. A suite that only covers the happy path proves
the API works when nothing goes wrong, which is not the interesting half.
"""

import pytest


class TestNotFound:
    """Every endpoint taking an id must 404 on a missing one."""

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
    def test_missing_task_returns_404(self, client, method, path):
        payload = {"title": "Does not matter"} if method in ("put", "patch") else None
        response = client.request(method.upper(), path, json=payload)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_404_message_is_the_same_from_every_endpoint(self, client):
        """_require() words it once, so a client sees one message."""
        messages = {
            client.get("/tasks/999").json()["error"]["message"],
            client.delete("/tasks/999").json()["error"]["message"],
            client.post("/tasks/999/complete").json()["error"]["message"],
        }
        assert messages == {"No task with id 999"}


class TestConflict:
    """409 cases."""

    def test_duplicate_title_is_rejected(self, client):
        client.post("/tasks", json={"title": "Unique title"})
        response = client.post("/tasks", json={"title": "Unique title"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"
        assert response.json()["error"]["details"][0]["field"] == "body.title"

    def test_completing_an_already_done_task_is_a_conflict(self, client):
        response = client.post("/tasks/4/complete")
        assert response.status_code == 409
        assert "already done" in response.json()["error"]["message"]

    def test_a_conflict_does_not_change_state(self, client):
        before = client.get("/tasks").json()["total"]
        client.post("/tasks", json={"title": "Renew domain"})
        assert client.get("/tasks").json()["total"] == before


class TestValidation:
    """422 cases, all produced by the schema rather than by handler code."""

    @pytest.mark.parametrize(
        "payload,expected_field",
        [
            ({}, "body.title"),
            ({"title": "x"}, "body.title"),
            ({"title": "x" * 200}, "body.title"),
            ({"title": "ok", "priority": "urgent"}, "body.priority"),
            ({"title": "ok", "tags": ["a"] * 20}, "body.tags"),
            ({"title": "ok", "description": "d" * 600}, "body.description"),
        ],
    )
    def test_bad_create_payload_is_422(self, client, payload, expected_field):
        response = client.post("/tasks", json=payload)
        assert response.status_code == 422
        fields = [d["field"] for d in response.json()["error"]["details"]]
        assert expected_field in fields

    def test_unknown_field_is_rejected(self, client):
        """extra="forbid" turns a client typo into an error rather than a silent drop."""
        response = client.post("/tasks", json={"title": "ok", "is_admin": True})
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "body.is_admin"

    def test_status_cannot_be_set_on_create(self, client):
        """TaskCreate has no status field, so sending one is an extra key."""
        response = client.post("/tasks", json={"title": "ok", "status": "done"})
        assert response.status_code == 422

    @pytest.mark.parametrize("path", ["/tasks/0", "/tasks/-1", "/tasks/abc"])
    def test_bad_path_parameter_is_422_not_404(self, client, path):
        """Malformed and not-found are different answers and must not collapse."""
        assert client.get(path).status_code == 422

    @pytest.mark.parametrize(
        "query", ["limit=0", "limit=500", "offset=-1", "status=archived", "priority=urgent", "q=a"]
    )
    def test_bad_query_parameter_is_422(self, client, query):
        assert client.get(f"/tasks?{query}").status_code == 422

    def test_a_failed_create_does_not_insert_anything(self, client):
        client.post("/tasks", json={"title": "x"})
        assert client.get("/tasks").json()["total"] == 4


class TestRoutingErrors:
    """Failures raised by the router, before any endpoint code runs."""

    def test_unknown_route_uses_the_envelope(self, client):
        response = client.get("/no-such-route")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_wrong_method_uses_the_envelope(self, client):
        response = client.post("/tasks/1")
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"
