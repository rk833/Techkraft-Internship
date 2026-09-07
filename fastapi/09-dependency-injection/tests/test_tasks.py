"""Behaviour tests carried forward from module 08.

Kept so the refactor onto dependencies can be shown not to have changed what
the API does. The endpoints were rewritten; these assertions were not.
"""

import pytest


class TestCrudStillWorks:
    def test_create_returns_201(self, client):
        response = client.post("/tasks", json={"title": "Still works"})
        assert response.status_code == 201
        assert response.json()["status"] == "todo"

    def test_get_one(self, client):
        assert client.get("/tasks/1").json()["title"] == "Write the module 08 README"

    def test_replace_resets_omitted_fields(self, client):
        after = client.put("/tasks/1", json={"title": "Replaced"}).json()
        assert after["tags"] == []
        assert after["priority"] == "medium"

    def test_patch_changes_only_what_was_sent(self, client):
        before = client.get("/tasks/1").json()
        after = client.patch("/tasks/1", json={"priority": "low"}).json()
        assert after["priority"] == "low"
        assert after["title"] == before["title"]

    def test_complete(self, client):
        assert client.post("/tasks/2/complete").json()["status"] == "done"

    def test_delete_returns_204_with_no_body(self, client):
        response = client.delete("/tasks/3")
        assert response.status_code == 204
        assert response.text == ""

    def test_filters(self, client):
        assert client.get("/tasks?status=todo").json()["total"] == 2
        assert client.get("/tasks?priority=high").json()["total"] == 2
        assert client.get("/tasks?q=renew").json()["total"] == 1


class TestErrorsStillWork:
    def test_duplicate_title_is_409(self, client):
        client.post("/tasks", json={"title": "Unique"})
        assert client.post("/tasks", json={"title": "Unique"}).status_code == 409

    def test_completing_a_done_task_is_409(self, client):
        assert client.post("/tasks/4/complete").status_code == 409

    @pytest.mark.parametrize(
        "payload", [{}, {"title": "x"}, {"title": "ok", "priority": "urgent"}, {"title": "ok", "nope": 1}]
    )
    def test_bad_payloads_are_422(self, client, payload):
        assert client.post("/tasks", json=payload).status_code == 422

    def test_unknown_route_uses_the_envelope(self, client):
        assert client.get("/no-such-route").json()["error"]["code"] == "not_found"


class TestContractStillHolds:
    @pytest.mark.parametrize("path", ["/health", "/tasks", "/tasks/999", "/admin/tasks"])
    def test_every_response_carries_the_middleware_headers(self, client, path):
        response = client.get(path)
        assert response.headers.get("x-request-id")
        assert float(response.headers["x-response-time-ms"]) >= 0

    @pytest.mark.parametrize("path", ["/tasks/999", "/admin/tasks", "/no-such-route"])
    def test_error_reference_matches_the_request_id(self, client, path):
        response = client.get(path)
        assert response.json()["error"]["reference"] == response.headers["x-request-id"]

    def test_the_500_still_carries_headers_and_cors(self, raw_client):
        response = raw_client.get(
            "/diagnostics/unit-of-work/fail", headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 500
        assert response.headers.get("x-request-id")
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_the_500_leaks_nothing(self, raw_client):
        text = raw_client.get("/diagnostics/unit-of-work/fail").text
        assert "Traceback" not in text
        assert "endpoint failed after" not in text
