"""Alembic environment.

Two things are set up here that the generated template does not do:

1. The database URL comes from application settings rather than from
   alembic.ini. One source of truth means alembic and the application can never
   be pointed at different databases, which is the single most confusing
   failure mode in this area.

2. target_metadata is the models' metadata, which is what makes `alembic
   revision --autogenerate` able to diff the models against the database.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# alembic/env.py -> 11-database/, so the app package is importable when alembic
# is invoked from the module root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  imported for its side effect

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

# ALEMBIC_DATABASE_URL lets the test suite point migrations at a throwaway
# database without editing any file.
import os  # noqa: E402

url = os.environ.get("ALEMBIC_DATABASE_URL") or settings.resolved_database_url
config.set_main_option("sqlalchemy.url", url)

# models must be imported before this line, or the metadata is empty and
# autogenerate cheerfully produces a migration that drops every table.
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Skip alembic's own bookkeeping table when diffing."""
    if type_ == "table" and name == "alembic_version":
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it.

    Useful when a DBA has to review and apply the change by hand, which is
    common in environments where the application has no DDL permissions.
    """
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            # compare_type detects a column type change. Off by default, which
            # means a String(32) widened to String(64) produces an empty
            # migration and silently never reaches the database.
            compare_type=True,
            compare_server_default=True,
            # SQLite cannot ALTER most things. Batch mode rebuilds the table
            # behind the scenes: create new, copy, drop old, rename. Without it
            # any ALTER COLUMN migration fails on SQLite while working fine on
            # PostgreSQL.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
