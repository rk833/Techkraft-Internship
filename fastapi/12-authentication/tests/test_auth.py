"""Registration, login, refresh, and the authentication boundary."""

import pytest

from app.models import User
from app.security import create_token
from tests.conftest import ALICE, TEST_SETTINGS, auth


class TestRegistration:
    def test_returns_201(self, client):
        response = client.post("/auth/register", json=ALICE)
        assert response.status_code == 201

    def test_the_password_is_not_in_the_response(self, client):
        body = client.post("/auth/register", json=ALICE).text
        assert "password" not in body
        assert ALICE["password"] not in body

    def test_the_password_is_stored_hashed(self, client, db_session):
        """The check that matters. Assert against the database, not the response."""
        client.post("/auth/register", json=ALICE)
        stored = db_session.query(User).filter_by(username="alice").one()
        assert stored.hashed_password != ALICE["password"]
        assert stored.hashed_password.startswith("$2b$")

    def test_two_users_with_the_same_password_get_different_hashes(self, client, db_session):
        """Proves the salt is per-user, so one cracked hash does not crack both."""
        shared = "identical-password"
        client.post("/auth/register", json={**ALICE, "password": shared})
        client.post("/auth/register", json={"username": "bob", "email": "bob@example.com", "password": shared})
        hashes = [u.hashed_password for u in db_session.query(User).all()]
        assert hashes[0] != hashes[1]

    def test_a_new_user_is_not_an_admin(self, client, db_session):
        """There is no route that grants the admin role on registration."""
        client.post("/auth/register", json=ALICE)
        assert db_session.query(User).filter_by(username="alice").one().role == "user"

    def test_role_cannot_be_set_at_registration(self, client):
        """extra="forbid" means privilege escalation via the body is a 422."""
        response = client.post("/auth/register", json={**ALICE, "role": "admin"})
        assert response.status_code == 422

    def test_a_duplicate_is_409(self, client, alice):
        assert client.post("/auth/register", json=ALICE).status_code == 409

    def test_the_conflict_message_does_not_say_which_field(self, client, alice):
        """"That email is taken" is a free account-existence oracle."""
        message = client.post("/auth/register", json=ALICE).json()["error"]["message"]
        assert "email" in message and "username" in message

    @pytest.mark.parametrize(
        "payload",
        [
            {**ALICE, "password": "short"},
            {**ALICE, "password": "x" * 73},
            {**ALICE, "email": "not-an-email"},
            {**ALICE, "username": "ab"},
            {**ALICE, "username": "has space"},
        ],
    )
    def test_bad_payloads_are_422(self, client, payload):
        assert client.post("/auth/register", json=payload).status_code == 422

    def test_a_73_byte_password_is_422_not_500(self, client):
        """bcrypt raises above 72 bytes, so the schema has to catch it first."""
        response = client.post("/auth/register", json={**ALICE, "password": "x" * 73})
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "body.password"


class TestLogin:
    def test_returns_a_token_pair(self, client, alice):
        body = client.post("/auth/login", data={"username": "alice", "password": ALICE["password"]}).json()
        assert body["token_type"] == "bearer"
        assert body["access_token"] and body["refresh_token"]
        assert body["expires_in"] > 0

    def test_a_wrong_password_is_401(self, client, alice):
        response = client.post("/auth/login", data={"username": "alice", "password": "wrong-password"})
        assert response.status_code == 401

    def test_an_unknown_user_is_401(self, client):
        response = client.post("/auth/login", data={"username": "nobody", "password": "any-password"})
        assert response.status_code == 401

    def test_both_failures_give_the_identical_message(self, client, alice):
        """Different messages would let an attacker enumerate valid usernames."""
        wrong_password = client.post("/auth/login", data={"username": "alice", "password": "wrong-password"})
        unknown_user = client.post("/auth/login", data={"username": "nobody", "password": "wrong-password"})
        assert wrong_password.json()["error"] | {"reference": ""} == unknown_user.json()["error"] | {"reference": ""}

    def test_a_disabled_account_cannot_log_in(self, client, alice, db_session):
        db_session.query(User).filter_by(username="alice").one().is_active = False
        db_session.commit()
        response = client.post("/auth/login", data={"username": "alice", "password": ALICE["password"]})
        assert response.status_code == 401

    def test_login_uses_form_encoding_not_json(self, client, alice):
        """The OAuth2 password flow is form-encoded, which is what Swagger posts."""
        as_json = client.post("/auth/login", json={"username": "alice", "password": ALICE["password"]})
        assert as_json.status_code == 422


class TestTheAuthenticationBoundary:
    PROTECTED = [
        ("get", "/auth/me"),
        ("get", "/notes"),
        ("post", "/notes"),
        ("get", "/notes/1"),
        ("patch", "/notes/1"),
        ("delete", "/notes/1"),
        ("get", "/admin/users"),
        ("get", "/admin/stats"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_no_token_is_401(self, client, method, path):
        payload = {"title": "Anything"} if method in ("post", "patch") else None
        assert client.request(method.upper(), path, json=payload).status_code == 401

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_a_garbage_token_is_401(self, client, method, path):
        payload = {"title": "Anything"} if method in ("post", "patch") else None
        response = client.request(
            method.upper(), path, json=payload, headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401

    def test_the_401_uses_the_standard_envelope(self, client):
        body = client.get("/auth/me").json()
        assert set(body["error"]) == {"code", "message", "details", "reference"}
        assert body["error"]["code"] == "unauthenticated"

    def test_the_error_does_not_say_why_the_token_failed(self, client, alice):
        """Expired versus forged is useful to us and useful to an attacker."""
        expired = create_token(alice["id"], "access", "user", TEST_SETTINGS, expires_delta=__import__("datetime").timedelta(seconds=-1))
        forged = "a.b.c"
        messages = {
            client.get("/auth/me", headers={"Authorization": f"Bearer {t}"}).json()["error"]["message"]
            for t in (expired, forged)
        }
        assert len(messages) == 1

    def test_an_expired_token_is_401(self, client, alice):
        from datetime import timedelta

        expired = create_token(alice["id"], "access", "user", TEST_SETTINGS, expires_delta=timedelta(seconds=-1))
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    def test_a_refresh_token_cannot_authorise_a_request(self, client, alice):
        """Otherwise every session silently lasts the refresh lifetime."""
        headers = {"Authorization": f"Bearer {alice['refresh_token']}"}
        assert client.get("/auth/me", headers=headers).status_code == 401

    def test_a_token_for_a_deleted_user_is_401(self, client, alice, db_session):
        """The token is still valid; the user is not.

        Checking only the signature would keep a deleted account working until
        its token expired.
        """
        db_session.query(User).filter_by(id=alice["id"]).delete()
        db_session.commit()
        assert client.get("/auth/me", headers=auth(alice)).status_code == 401

    def test_a_token_for_a_disabled_user_is_403(self, client, alice, db_session):
        """403, not 401: we know exactly who they are."""
        db_session.query(User).filter_by(id=alice["id"]).one().is_active = False
        db_session.commit()
        assert client.get("/auth/me", headers=auth(alice)).status_code == 403

    def test_a_valid_token_works(self, client, alice):
        body = client.get("/auth/me", headers=auth(alice)).json()
        assert body["username"] == "alice"
        assert "password" not in body


class TestRefresh:
    def test_a_refresh_token_yields_a_new_pair(self, client, alice):
        response = client.post("/auth/refresh", json={"refresh_token": alice["refresh_token"]})
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_the_new_access_token_works(self, client, alice):
        new = client.post("/auth/refresh", json={"refresh_token": alice["refresh_token"]}).json()
        headers = {"Authorization": f"Bearer {new['access_token']}"}
        assert client.get("/auth/me", headers=headers).status_code == 200

    def test_an_access_token_cannot_be_refreshed(self, client, alice):
        response = client.post("/auth/refresh", json={"refresh_token": alice["access_token"]})
        assert response.status_code == 401

    def test_a_deleted_user_cannot_refresh(self, client, alice, db_session):
        db_session.query(User).filter_by(id=alice["id"]).delete()
        db_session.commit()
        assert client.post("/auth/refresh", json={"refresh_token": alice["refresh_token"]}).status_code == 401

    def test_a_garbage_refresh_token_is_401(self, client):
        assert client.post("/auth/refresh", json={"refresh_token": "nonsense"}).status_code == 401


class TestChangePassword:
    def test_it_works(self, client, alice):
        response = client.post(
            "/auth/change-password",
            json={"current_password": ALICE["password"], "new_password": "brand-new-password"},
            headers=auth(alice),
        )
        assert response.status_code == 204

    def test_the_new_password_logs_in(self, client, alice):
        client.post(
            "/auth/change-password",
            json={"current_password": ALICE["password"], "new_password": "brand-new-password"},
            headers=auth(alice),
        )
        assert client.post("/auth/login", data={"username": "alice", "password": "brand-new-password"}).status_code == 200

    def test_the_old_password_stops_working(self, client, alice):
        client.post(
            "/auth/change-password",
            json={"current_password": ALICE["password"], "new_password": "brand-new-password"},
            headers=auth(alice),
        )
        assert client.post("/auth/login", data={"username": "alice", "password": ALICE["password"]}).status_code == 401

    def test_the_current_password_is_required_even_when_authenticated(self, client, alice):
        """A stolen access token must not be enough to take over an account."""
        response = client.post(
            "/auth/change-password",
            json={"current_password": "wrong-password", "new_password": "brand-new-password"},
            headers=auth(alice),
        )
        assert response.status_code == 401

    def test_the_new_password_must_differ(self, client, alice):
        response = client.post(
            "/auth/change-password",
            json={"current_password": ALICE["password"], "new_password": ALICE["password"]},
            headers=auth(alice),
        )
        assert response.status_code == 422

    def test_it_requires_authentication(self, client):
        response = client.post(
            "/auth/change-password",
            json={"current_password": "a-password-1", "new_password": "b-password-1"},
        )
        assert response.status_code == 401
