"""Note endpoint tests, ORM behaviour, and the N+1 demonstration."""

import pytest

from app.models import Note


class TestCreate:
    def test_returns_201(self, client, user):
        response = client.post(f"/users/{user['id']}/notes", json={"title": "First note"})
        assert response.status_code == 201
        assert response.json()["author_id"] == user["id"]

    def test_archived_defaults_to_false(self, client, user):
        """The column added by the second migration has a working default."""
        body = client.post(f"/users/{user['id']}/notes", json={"title": "Fresh note"}).json()
        assert body["archived"] is False

    def test_body_defaults_to_empty_string(self, client, user):
        assert client.post(f"/users/{user['id']}/notes", json={"title": "No body"}).json()["body"] == ""

    def test_creating_for_a_missing_user_is_404(self, client):
        assert client.post("/users/9999/notes", json={"title": "Orphan"}).status_code == 404

    def test_a_failed_create_persists_nothing(self, client, db_session):
        client.post("/users/9999/notes", json={"title": "Orphan"})
        assert db_session.query(Note).count() == 0


class TestRead:
    def test_get_one(self, client, notes):
        assert client.get(f"/notes/{notes[0]['id']}").json()["title"] == "Note number 0"

    def test_missing_note_is_404(self, client):
        assert client.get("/notes/9999").status_code == 404

    def test_list_for_a_user(self, client, user, notes):
        body = client.get(f"/users/{user['id']}/notes").json()
        assert body["total"] == 3

    def test_a_users_notes_do_not_include_another_users(self, client, user, other_user, notes):
        client.post(f"/users/{other_user['id']}/notes", json={"title": "Not yours"})
        titles = [n["title"] for n in client.get(f"/users/{user['id']}/notes").json()["items"]]
        assert "Not yours" not in titles

    def test_search_filters_in_sql(self, client, user, notes):
        body = client.get(f"/users/{user['id']}/notes?q=number 1").json()
        assert body["total"] == 1

    def test_search_is_case_insensitive(self, client, user, notes):
        assert client.get(f"/users/{user['id']}/notes?q=NOTE NUMBER").json()["total"] == 3

    def test_archived_filter(self, client, user, notes):
        client.patch(f"/notes/{notes[0]['id']}", json={"archived": True})
        assert client.get(f"/users/{user['id']}/notes?archived=true").json()["total"] == 1
        assert client.get(f"/users/{user['id']}/notes?archived=false").json()["total"] == 2

    def test_filtering_happens_in_the_database(self, client, user, notes, query_counter):
        """One SELECT for the count, one for the page, whatever the filter.

        A filter applied in Python after loading everything would still return
        the right answer, so only the query count distinguishes them.
        """
        with query_counter() as counter:
            client.get(f"/users/{user['id']}/notes?q=number&archived=false")
        assert counter.count_of("SELECT") <= 3


class TestUpdate:
    def test_patch_changes_only_what_was_sent(self, client, notes):
        before = notes[0]
        after = client.patch(f"/notes/{before['id']}", json={"title": "Renamed"}).json()
        assert after["title"] == "Renamed"
        assert after["body"] == before["body"]

    def test_updated_at_moves_but_created_at_does_not(self, client, notes):
        before = client.get(f"/notes/{notes[0]['id']}").json()
        after = client.patch(f"/notes/{notes[0]['id']}", json={"title": "Touched"}).json()
        assert after["created_at"] == before["created_at"]
        assert after["updated_at"] >= before["updated_at"]

    def test_the_change_is_persisted(self, client, notes, db_session):
        client.patch(f"/notes/{notes[0]['id']}", json={"title": "Persisted"})
        db_session.expire_all()
        assert db_session.get(Note, notes[0]["id"]).title == "Persisted"

    def test_empty_patch_is_a_no_op(self, client, notes):
        before = client.get(f"/notes/{notes[0]['id']}").json()
        after = client.patch(f"/notes/{notes[0]['id']}", json={}).json()
        assert after["title"] == before["title"]

    @pytest.mark.parametrize("payload", [{"title": "x"}, {"title": None}, {"nope": 1}])
    def test_bad_patch_is_422(self, client, notes, payload):
        assert client.patch(f"/notes/{notes[0]['id']}", json=payload).status_code == 422


class TestDelete:
    def test_returns_204(self, client, notes):
        response = client.delete(f"/notes/{notes[0]['id']}")
        assert response.status_code == 204
        assert response.text == ""

    def test_the_row_is_gone(self, client, notes, db_session):
        client.delete(f"/notes/{notes[0]['id']}")
        assert db_session.get(Note, notes[0]["id"]) is None

    def test_the_user_survives(self, client, user, notes):
        client.delete(f"/notes/{notes[0]['id']}")
        assert client.get(f"/users/{user['id']}").status_code == 200


class TestNPlusOne:
    """The problem, and the fix, counted rather than described."""

    @pytest.fixture
    def many_notes(self, client, user, other_user):
        for i in range(10):
            owner = user if i % 2 == 0 else other_user
            client.post(f"/users/{owner['id']}/notes", json={"title": f"Bulk note {i}"})

    def test_both_endpoints_return_the_same_data(self, client, many_notes):
        lazy = client.get("/notes?limit=10").json()
        eager = client.get("/notes/eager?limit=10").json()
        assert lazy == eager

    def test_the_lazy_endpoint_issues_one_query_per_row(self, client, many_notes, query_counter):
        with query_counter() as counter:
            client.get("/notes?limit=10")
        # 1 for the notes, plus 1 per note to load its author. The identity map
        # spares repeats for an author already loaded, so with two distinct
        # authors this is well below 11 - but it still scales with the number
        # of distinct authors rather than being constant.
        assert counter.count_of("SELECT") > 2

    def test_the_eager_endpoint_is_constant(self, client, many_notes, query_counter):
        with query_counter() as counter:
            client.get("/notes/eager?limit=10")
        assert counter.count_of("SELECT") == 2

    def test_eager_stays_constant_as_the_page_grows(self, client, user, other_user, query_counter):
        """The property that matters: it does not scale with row count."""
        for i in range(20):
            owner = user if i % 2 == 0 else other_user
            client.post(f"/users/{owner['id']}/notes", json={"title": f"Scaling note {i}"})
        with query_counter() as counter:
            client.get("/notes/eager?limit=20")
        assert counter.count_of("SELECT") == 2


class TestSessionLifecycle:
    """The dependency commits on success and rolls back on failure."""

    def test_a_successful_request_commits(self, client, user, db_session):
        client.post(f"/users/{user['id']}/notes", json={"title": "Committed note"})
        db_session.expire_all()
        assert db_session.query(Note).filter_by(title="Committed note").count() == 1

    def test_a_404_partway_through_leaves_nothing_behind(self, client, db_session):
        client.post("/users/9999/notes", json={"title": "Never stored"})
        assert db_session.query(Note).filter_by(title="Never stored").count() == 0

    def test_an_unexpected_failure_rolls_back(self, raw_client, user, db_session, monkeypatch):
        """Force a failure after the insert is pending but before it commits.

        Targeted at the one object rather than counting flush calls, so the
        test does not depend on how many times SQLAlchemy happens to flush.
        """
        from sqlalchemy.orm import Session as SASession

        original_flush = SASession.flush

        def exploding_flush(self, *args, **kwargs):
            if any(isinstance(obj, Note) and obj.title == "Doomed" for obj in self.new):
                raise RuntimeError("simulated failure after insert")
            return original_flush(self, *args, **kwargs)

        monkeypatch.setattr(SASession, "flush", exploding_flush)
        response = raw_client.post(f"/users/{user['id']}/notes", json={"title": "Doomed"})
        monkeypatch.undo()

        assert response.status_code == 500
        db_session.expire_all()
        assert db_session.query(Note).filter_by(title="Doomed").count() == 0


class TestNoResidue:
    """Two tests that only both pass because each is rolled back."""

    def test_a_creates_notes(self, client, user, notes):
        assert client.get(f"/users/{user['id']}/notes").json()["total"] == 3

    def test_b_starts_from_an_empty_database(self, client, db_session):
        assert db_session.query(Note).count() == 0
