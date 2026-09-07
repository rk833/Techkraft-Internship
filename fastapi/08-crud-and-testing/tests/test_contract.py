"""Contract tests.

These assert the shape of the API rather than any single behaviour: that the
error envelope is identical across every failure, that the middleware headers
are always present, and that no response leaks internals. They are the tests
that catch a regression in a cross-cutting concern, which per-endpoint tests
cannot.
"""

import pytest

pytestmark = pytest.mark.contract

ERROR_PATHS = [
    ("get", "/tasks/999", None),
    ("post", "/tasks", {}),
    ("post", "/tasks/4/complete", None),
    ("get", "/tasks/abc", None),
    ("get", "/no-such-route", None),
    ("post", "/tasks/1", None),
]


class TestErrorEnvelope:
    """Every failure, at every status code, is the same shape."""

    @pytest.mark.parametrize("method,path,payload", ERROR_PATHS)
    def test_shape_is_identical(self, client, method, path, payload):
        body = client.request(method.upper(), path, json=payload).json()
        assert set(body) == {"error"}
        assert set(body["error"]) == {"code", "message", "details", "reference"}

    @pytest.mark.parametrize("method,path,payload", ERROR_PATHS)
    def test_reference_matches_the_request_id_header(self, client, method, path, payload):
        response = client.request(method.upper(), path, json=payload)
        assert response.json()["error"]["reference"] == response.headers["x-request-id"]

    def test_the_500_path_is_also_covered(self, raw_client, monkeypatch):
        """Break the store so a genuinely unexpected exception escapes.

        monkeypatch undoes itself when the test ends, so nothing leaks into the
        next test. Without a case like this the catch-all handler is never
        exercised by the suite.
        """
        import store as store_module

        def explode(self):
            raise RuntimeError("simulated store failure")

        monkeypatch.setattr(store_module.TaskStore, "list", explode)
        response = raw_client.get("/tasks")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert set(response.json()["error"]) == {"code", "message", "details", "reference"}

    def test_the_500_response_leaks_nothing(self, raw_client, monkeypatch):
        import store as store_module

        def explode(self):
            raise RuntimeError("secret connection string postgres://user:pw@host/db")

        monkeypatch.setattr(store_module.TaskStore, "list", explode)
        text = raw_client.get("/tasks").text
        assert "Traceback" not in text
        assert "postgres://" not in text
        assert "store.py" not in text

    def test_the_500_still_carries_the_middleware_headers(self, raw_client, monkeypatch):
        """Regression guard for the module 07 bug.

        A 500 generated outside the middleware stack has no request id and no
        CORS headers. This test fails if that regresses.
        """
        import store as store_module

        monkeypatch.setattr(
            store_module.TaskStore, "list", lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        response = raw_client.get("/tasks", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 500
        assert response.headers.get("x-request-id")
        assert response.headers.get("x-response-time-ms")
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestHeaders:
    """Middleware guarantees, asserted rather than assumed."""

    @pytest.mark.parametrize(
        "method,path",
        [("get", "/health"), ("get", "/tasks"), ("get", "/tasks/1"), ("get", "/tasks/999"), ("get", "/docs")],
    )
    def test_every_response_has_a_request_id_and_timing(self, client, method, path):
        response = client.request(method.upper(), path)
        assert response.headers.get("x-request-id")
        assert float(response.headers["x-response-time-ms"]) >= 0

    def test_request_ids_are_unique_per_request(self, client):
        ids = {client.get("/health").headers["x-request-id"] for _ in range(10)}
        assert len(ids) == 10

    def test_a_valid_client_request_id_is_honoured(self, client):
        response = client.get("/health", headers={"x-request-id": "trace-abcdef123456"})
        assert response.headers["x-request-id"] == "trace-abcdef123456"

    @pytest.mark.parametrize("bad", ["abc", "x" * 200, "aa\r\nX-Admin: true", "abc<script>"])
    def test_an_unsafe_client_request_id_is_replaced(self, client, bad):
        response = client.get("/health", headers={"x-request-id": bad})
        assert response.headers["x-request-id"] != bad

    def test_security_headers_are_present(self, client):
        headers = client.get("/health").headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"


class TestOpenAPI:
    """The generated schema is part of the contract too."""

    def test_every_task_route_documents_the_error_shape(self, client):
        schema = client.get("/openapi.json").json()
        for path, operations in schema["paths"].items():
            if not path.startswith("/tasks"):
                continue
            for method, operation in operations.items():
                assert "404" in operation["responses"], f"{method} {path}"

    def test_create_schema_has_no_status_field(self, client):
        schema = client.get("/openapi.json").json()
        assert "status" not in schema["components"]["schemas"]["TaskCreate"]["properties"]

    def test_replace_schema_does_have_status(self, client):
        schema = client.get("/openapi.json").json()
        assert "status" in schema["components"]["schemas"]["TaskReplace"]["properties"]
