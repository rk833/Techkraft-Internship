"""User endpoint tests, including the constraints the database enforces."""

import pytest

from app.models import Note, User


class TestCreate:
    def test_returns_201_with_a_real_id(self, client):
        response = client.post("/users", json={"username": "ada", "email": "ada@example.com"})
        assert response.status_code == 201
        assert response.json()["id"] > 0

    def test_the_row_is_actually_in_the_database(self, client, db_session):
        """Assert against the database, not only against the response.

        A handler could build a plausible response without persisting anything,
        and an endpoint-only test would not notice.
        """
        client.post("/users", json={"username": "ada", "email": "ada@example.com"})
        stored = db_session.query(User).filter_by(username="ada").one()
        assert stored.email == "ada@example.com"

    def test_created_at_is_populated_by_the_default(self, client):
        assert client.post(
            "/users", json={"username": "ada", "email": "ada@example.com"}
        ).json()["created_at"]

    def test_duplicate_username_is_409(self, client, user):
        response = client.post("/users", json={"username": "ada", "email": "other@example.com"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_duplicate_email_is_409(self, client, user):
        response = client.post("/users", json={"username": "different", "email": "ada@example.com"})
        assert response.status_code == 409

    def test_a_rejected_duplicate_inserts_nothing(self, client, user, db_session):
        client.post("/users", json={"username": "ada", "email": "other@example.com"})
        assert db_session.query(User).count() == 1

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"username": "ab", "email": "a@b.com"},
            {"username": "ada", "email": "not-an-email"},
            {"username": "has space", "email": "a@b.com"},
            {"username": "ada", "email": "a@b.com", "is_admin": True},
        ],
    )
    def test_bad_payload_is_422(self, client, payload):
        assert client.post("/users", json=payload).status_code == 422


class TestRead:
    def test_get_one(self, client, user):
        assert client.get(f"/users/{user['id']}").json()["username"] == "ada"

    def test_note_count_is_included(self, client, user, notes):
        assert client.get(f"/users/{user['id']}").json()["note_count"] == 3

    def test_note_count_is_zero_for_a_new_user(self, client, user):
        assert client.get(f"/users/{user['id']}").json()["note_count"] == 0

    def test_missing_user_is_404(self, client):
        response = client.get("/users/9999")
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "No user with id 9999"

    def test_list_is_paginated(self, client, user, other_user):
        body = client.get("/users?limit=1").json()
        assert body["total"] == 2
        assert body["count"] == 1

    def test_the_total_is_a_count_query_not_the_page_size(self, client, user, other_user, query_counter):
        with query_counter() as counter:
            body = client.get("/users?limit=1").json()
        assert body["total"] == 2
        assert counter.count_of("SELECT") == 2


class TestCascadeDelete:
    """Deleting a user must take their notes with them."""

    def test_the_user_is_gone(self, client, user, notes):
        assert client.delete(f"/users/{user['id']}").status_code == 204
        assert client.get(f"/users/{user['id']}").status_code == 404

    def test_the_notes_go_too(self, client, user, notes, db_session):
        client.delete(f"/users/{user['id']}")
        assert db_session.query(Note).count() == 0

    def test_no_orphaned_rows_survive(self, client, user, notes, db_session):
        """The check that catches a missing FK enforcement.

        Without PRAGMA foreign_keys=ON, SQLite accepts the delete and leaves
        the notes pointing at a user id that no longer exists. The same code
        against PostgreSQL would behave differently, which is the worst kind of
        difference to discover in production.
        """
        client.delete(f"/users/{user['id']}")
        orphans = (
            db_session.query(Note)
            .outerjoin(User, Note.author_id == User.id)
            .filter(User.id.is_(None))
            .count()
        )
        assert orphans == 0

    def test_another_users_notes_are_untouched(self, client, user, other_user, notes, db_session):
        client.post(f"/users/{other_user['id']}/notes", json={"title": "Survivor note"})
        client.delete(f"/users/{user['id']}")
        remaining = db_session.query(Note).all()
        assert len(remaining) == 1
        assert remaining[0].title == "Survivor note"
