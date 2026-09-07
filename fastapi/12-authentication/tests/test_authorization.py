"""Authorisation: what an authenticated caller is allowed to do.

Authentication is "who are you". Authorisation is "may you". Every test here
uses a perfectly valid token, which is what makes them authorisation tests.
"""

import pytest

from app.models import Note, User
from tests.conftest import auth


class TestOwnershipIsolation:
    """The headline requirement: alice cannot touch bob's notes."""

    @pytest.fixture
    def bobs_note(self, client, bob) -> dict:
        response = client.post("/notes", json={"title": "Bob private note"}, headers=auth(bob))
        assert response.status_code == 201
        return response.json()

    def test_alice_cannot_read_bobs_note(self, client, alice, bobs_note):
        assert client.get(f"/notes/{bobs_note['id']}", headers=auth(alice)).status_code == 404

    def test_alice_cannot_update_bobs_note(self, client, alice, bobs_note):
        response = client.patch(
            f"/notes/{bobs_note['id']}", json={"title": "Hijacked"}, headers=auth(alice)
        )
        assert response.status_code == 404

    def test_a_failed_update_does_not_change_anything(self, client, alice, bobs_note, db_session):
        client.patch(f"/notes/{bobs_note['id']}", json={"title": "Hijacked"}, headers=auth(alice))
        db_session.expire_all()
        assert db_session.get(Note, bobs_note["id"]).title == "Bob private note"

    def test_alice_cannot_delete_bobs_note(self, client, alice, bobs_note, db_session):
        assert client.delete(f"/notes/{bobs_note['id']}", headers=auth(alice)).status_code == 404
        db_session.expire_all()
        assert db_session.get(Note, bobs_note["id"]) is not None

    def test_bob_can_do_all_of_it(self, client, bob, bobs_note):
        assert client.get(f"/notes/{bobs_note['id']}", headers=auth(bob)).status_code == 200
        assert client.patch(f"/notes/{bobs_note['id']}", json={"title": "Mine"}, headers=auth(bob)).status_code == 200
        assert client.delete(f"/notes/{bobs_note['id']}", headers=auth(bob)).status_code == 204

    def test_the_list_endpoint_shows_only_your_own(self, client, alice, bob, alice_notes, bobs_note):
        alice_titles = [n["title"] for n in client.get("/notes", headers=auth(alice)).json()["items"]]
        bob_titles = [n["title"] for n in client.get("/notes", headers=auth(bob)).json()["items"]]
        assert "Bob private note" not in alice_titles
        assert all(t.startswith("Alice") for t in alice_titles)
        assert bob_titles == ["Bob private note"]

    def test_the_total_count_is_also_scoped(self, client, alice, bob, alice_notes, bobs_note):
        """A leaking total would disclose how many notes other people have."""
        assert client.get("/notes", headers=auth(alice)).json()["total"] == 3
        assert client.get("/notes", headers=auth(bob)).json()["total"] == 1

    def test_someone_elses_note_is_404_not_403(self, client, alice, bobs_note):
        """403 would confirm the id exists, which is an enumeration oracle.

        404 makes "not yours" and "does not exist" indistinguishable from
        outside.
        """
        real_but_not_yours = client.get(f"/notes/{bobs_note['id']}", headers=auth(alice))
        does_not_exist = client.get("/notes/999999", headers=auth(alice))
        assert real_but_not_yours.status_code == does_not_exist.status_code == 404
        assert (
            real_but_not_yours.json()["error"]["code"] == does_not_exist.json()["error"]["code"]
        )

    def test_the_author_cannot_be_forged_at_creation(self, client, alice, bob):
        """NoteCreate has no author_id field, so there is nothing to forge."""
        response = client.post(
            "/notes", json={"title": "Framed", "author_id": bob["id"]}, headers=auth(alice)
        )
        assert response.status_code == 422

    def test_a_created_note_belongs_to_the_token_holder(self, client, alice, db_session):
        note_id = client.post("/notes", json={"title": "Mine"}, headers=auth(alice)).json()["id"]
        assert db_session.get(Note, note_id).author_id == alice["id"]


class TestRoleBasedAccess:
    ADMIN_ROUTES = [
        ("get", "/admin/users"),
        ("get", "/admin/stats"),
    ]

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_a_normal_user_gets_403(self, client, alice, method, path):
        """403, not 401. The caller is authenticated; they are just not allowed.

        Returning 401 here tells a client to log in again, which cannot help
        and produces a re-authentication loop.
        """
        response = client.request(method.upper(), path, headers=auth(alice))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_no_token_gets_401_not_403(self, client, method, path):
        """The two failures are distinct and must not be conflated."""
        assert client.request(method.upper(), path).status_code == 401

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES)
    def test_an_admin_gets_through(self, client, admin, method, path):
        assert client.request(method.upper(), path, headers=auth(admin)).status_code == 200

    def test_a_forged_role_claim_does_not_grant_access(self, client, alice):
        """The role is re-read from the database, not taken from the token.

        Even if an attacker could mint a signed token - which they cannot -
        editing the role claim would not help.
        """
        import jwt

        from tests.conftest import TEST_SETTINGS

        claims = jwt.decode(alice["access_token"], options={"verify_signature": False})
        claims["role"] = "admin"
        forged = jwt.encode(claims, TEST_SETTINGS.jwt_secret_key, algorithm="HS256")
        response = client.get("/admin/users", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 403

    def test_a_demotion_takes_effect_immediately(self, client, admin, db_session):
        """Not when the token expires.

        require_admin reads the row, so revoking a privilege is instant. Had it
        trusted the token's role claim, a demoted admin would keep full access
        for the remaining lifetime of their token.
        """
        assert client.get("/admin/stats", headers=auth(admin)).status_code == 200
        db_session.query(User).filter_by(id=admin["id"]).one().role = "user"
        db_session.commit()
        assert client.get("/admin/stats", headers=auth(admin)).status_code == 403


class TestAdminCapabilities:
    def test_an_admin_can_promote_a_user(self, client, admin, alice):
        response = client.patch(
            f"/admin/users/{alice['id']}/role", json={"role": "admin"}, headers=auth(admin)
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_the_promoted_user_can_then_use_admin_routes(self, client, admin, alice):
        client.patch(f"/admin/users/{alice['id']}/role", json={"role": "admin"}, headers=auth(admin))
        assert client.get("/admin/stats", headers=auth(alice)).status_code == 200

    def test_an_admin_cannot_demote_themselves(self, client, admin):
        """Otherwise the last admin can lock everyone out with one request."""
        response = client.patch(
            f"/admin/users/{admin['id']}/role", json={"role": "user"}, headers=auth(admin)
        )
        assert response.status_code == 403

    def test_an_admin_cannot_deactivate_themselves(self, client, admin):
        assert client.post(f"/admin/users/{admin['id']}/deactivate", headers=auth(admin)).status_code == 403

    def test_an_admin_cannot_delete_themselves(self, client, admin):
        assert client.delete(f"/admin/users/{admin['id']}", headers=auth(admin)).status_code == 403

    def test_deactivating_a_user_locks_them_out_immediately(self, client, admin, alice):
        assert client.get("/auth/me", headers=auth(alice)).status_code == 200
        client.post(f"/admin/users/{alice['id']}/deactivate", headers=auth(admin))
        assert client.get("/auth/me", headers=auth(alice)).status_code == 403

    def test_reactivating_restores_access(self, client, admin, alice):
        client.post(f"/admin/users/{alice['id']}/deactivate", headers=auth(admin))
        client.post(f"/admin/users/{alice['id']}/activate", headers=auth(admin))
        assert client.get("/auth/me", headers=auth(alice)).status_code == 200

    def test_an_admin_can_read_any_note(self, client, admin, alice, alice_notes):
        """Deliberate: moderation needs it. The audit log is what makes it safe."""
        assert client.get(f"/notes/{alice_notes[0]['id']}", headers=auth(admin)).status_code == 200

    def test_deleting_a_user_cascades_to_their_notes(self, client, admin, alice, alice_notes, db_session):
        client.delete(f"/admin/users/{alice['id']}", headers=auth(admin))
        db_session.expire_all()
        assert db_session.query(Note).filter_by(author_id=alice["id"]).count() == 0

    def test_admin_user_listing_never_includes_hashes(self, client, admin, alice):
        body = client.get("/admin/users", headers=auth(admin)).text
        assert "$2b$" not in body
        assert "hashed_password" not in body


class TestOpenAPI:
    def test_the_security_scheme_is_documented(self, client):
        """This is what gives Swagger UI its Authorize button."""
        schema = client.get("/openapi.json").json()
        assert "OAuth2PasswordBearer" in schema["components"]["securitySchemes"]

    def test_protected_routes_declare_security(self, client):
        schema = client.get("/openapi.json").json()
        assert "security" in schema["paths"]["/notes"]["get"]

    def test_register_and_login_do_not_require_security(self, client):
        schema = client.get("/openapi.json").json()
        assert "security" not in schema["paths"]["/auth/register"]["post"]
        assert "security" not in schema["paths"]["/auth/login"]["post"]

    def test_no_schema_exposes_a_password_field(self, client):
        """A response schema with a password field is a bug in the contract."""
        schema = client.get("/openapi.json").json()
        for name, model in schema["components"]["schemas"].items():
            if name.endswith("Read"):
                assert "password" not in model.get("properties", {}), name
                assert "hashed_password" not in model.get("properties", {}), name
