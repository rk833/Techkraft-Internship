"""Migration tests.

The first one here is the most valuable test in the module. It catches the
failure that quietly ruins a schema over months: someone edits a model, does
not generate a migration, and everything keeps working locally because the
development database was created from the models long ago.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.database import Base
from app import models  # noqa: F401  imported so the metadata is populated

pytestmark = pytest.mark.migrations


def _alembic_config(module_root) -> Config:
    cfg = Config(str(module_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(module_root / "alembic"))
    return cfg


class TestSchemaMatchesModels:
    def test_no_pending_migration(self, test_engine):
        """The models and the migrated schema must agree.

        compare_metadata is what `alembic revision --autogenerate` runs to
        decide what to write. An empty diff means running autogenerate now
        would produce nothing, which is the definition of being in sync.

        Without this test, forgetting to generate a migration is invisible
        until a deployment builds the schema from migrations alone and a column
        the code needs is not there.
        """
        with test_engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "include_object": lambda o, n, t, r, c: not (t == "table" and n == "alembic_version"),
                },
            )
            diff = compare_metadata(context, Base.metadata)

        assert diff == [], f"models and migrations have diverged: {diff}"


class TestMigrationHistory:
    def test_there_are_two_revisions(self, test_engine):
        script = ScriptDirectory.from_config(_alembic_config(_module_root()))
        revisions = list(script.walk_revisions())
        assert len(revisions) == 2

    def test_the_history_is_a_single_chain(self, test_engine):
        """Two heads means someone branched, and `upgrade head` becomes ambiguous."""
        script = ScriptDirectory.from_config(_alembic_config(_module_root()))
        assert len(script.get_heads()) == 1

    def test_the_database_is_at_head(self, test_engine):
        script = ScriptDirectory.from_config(_alembic_config(_module_root()))
        with test_engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        assert current == script.get_current_head()


class TestMigratedSchema:
    def test_both_tables_exist(self, test_engine):
        assert set(inspect(test_engine).get_table_names()) >= {"users", "notes", "alembic_version"}

    def test_the_second_migration_added_the_archived_column(self, test_engine):
        """The column exists because a migration added it, not create_all."""
        columns = {c["name"] for c in inspect(test_engine).get_columns("notes")}
        assert "archived" in columns

    def test_archived_is_not_nullable_and_has_a_server_default(self, test_engine):
        column = next(c for c in inspect(test_engine).get_columns("notes") if c["name"] == "archived")
        assert column["nullable"] is False
        assert column["default"] is not None

    def test_the_foreign_key_cascades(self, test_engine):
        fks = inspect(test_engine).get_foreign_keys("notes")
        assert fks[0]["referred_table"] == "users"
        assert fks[0]["options"].get("ondelete") == "CASCADE"

    def test_the_unique_indexes_exist(self, test_engine):
        indexes = {i["name"]: i for i in inspect(test_engine).get_indexes("users")}
        assert indexes["ix_users_username"]["unique"]
        assert indexes["ix_users_email"]["unique"]

    def test_the_composite_index_exists(self, test_engine):
        indexes = {i["name"]: i["column_names"] for i in inspect(test_engine).get_indexes("notes")}
        assert indexes["ix_notes_author_created"] == ["author_id", "created_at"]


class TestDowngrade:
    def test_the_history_round_trips(self, tmp_path, monkeypatch):
        """Upgrade to head, downgrade to base, upgrade again.

        A downgrade nobody ever runs is a downgrade that does not work, and the
        moment it is needed is the moment nobody wants to find that out. Run
        against a throwaway file so the session database is untouched.
        """
        db_file = tmp_path / "roundtrip.db"
        url = f"sqlite:///{db_file.as_posix()}"
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
        cfg = _alembic_config(_module_root())

        command.upgrade(cfg, "head")
        engine = create_engine(url)
        assert "notes" in inspect(engine).get_table_names()

        command.downgrade(cfg, "base")
        assert "notes" not in inspect(engine).get_table_names()

        command.upgrade(cfg, "head")
        assert "archived" in {c["name"] for c in inspect(engine).get_columns("notes")}
        engine.dispose()

    def test_downgrading_one_step_removes_only_the_archived_column(self, tmp_path, monkeypatch):
        db_file = tmp_path / "onestep.db"
        url = f"sqlite:///{db_file.as_posix()}"
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
        cfg = _alembic_config(_module_root())

        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")

        engine = create_engine(url)
        columns = {c["name"] for c in inspect(engine).get_columns("notes")}
        assert "archived" not in columns
        assert "title" in columns
        engine.dispose()


def _module_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
