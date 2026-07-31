"""
Checks for the API that cost nothing.

Everything here uses FastAPI's TestClient, which calls the app in process
without opening a port. Auth, validation and health are all testable without
touching the model, which is most of what can actually go wrong in a service.

Usage:
    python test_api.py           free checks only
    python test_api.py --live    also send one real chat request
"""

import sys

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)
KEY = {"X-API-Key": "local-dev-key"}

passed = failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok    {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} {detail}")


print("free checks, no model calls")

response = client.get("/health")
check("health returns 200", response.status_code == 200, response.text)
check("health reports a model", "model" in response.json())
check("health needs no auth", "X-API-Key" not in response.request.headers)

response = client.post("/chat", json={"message": "hi"})
check("chat without a key is 401", response.status_code == 401, response.text)

response = client.post("/chat", json={"message": "hi"}, headers={"X-API-Key": "wrong"})
check("chat with a bad key is 401", response.status_code == 401, response.text)

response = client.post("/chat", json={"message": ""}, headers=KEY)
check("empty message is rejected", response.status_code == 422, response.text)

response = client.post("/chat", json={"message": "x" * 5000}, headers=KEY)
check("oversized message is rejected", response.status_code == 422, response.text)

response = client.post("/chat", json={"message": "hi", "temperature": 9}, headers=KEY)
check("out of range temperature is rejected", response.status_code == 422, response.text)

response = client.post("/chat", json={}, headers=KEY)
check("missing message is rejected", response.status_code == 422, response.text)

response = client.get("/config", headers=KEY)
body = response.json() if response.status_code == 200 else {}
check("config returns 200", response.status_code == 200, response.text)
check("config counts keys rather than listing them", "api_keys_configured" in body)
check(
    "config leaks no secret",
    "GOOGLE_API_KEY" not in response.text and "AIza" not in response.text,
)

response = client.get("/health")
check("response carries a request id", "X-Request-ID" in response.headers)

sent = client.get("/health", headers={"X-Request-ID": "my-trace-123"})
check(
    "a supplied request id is echoed",
    sent.headers.get("X-Request-ID") == "my-trace-123",
    sent.headers.get("X-Request-ID", ""),
)

if "--live" in sys.argv:
    print()
    print("live check, one model call")
    response = client.post("/chat", json={"message": "Say hello in five words."}, headers=KEY)
    check("chat returns 200", response.status_code == 200, response.text)
    if response.status_code == 200:
        body = response.json()
        print(f"        reply: {body['reply']}")
        print(f"        model: {body['model']}, {body['latency_ms']}ms")
        check("reply is not empty", bool(body["reply"].strip()))
        check("token counts reported", body.get("output_tokens") is not None)

print()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
