"""add auth columns to users

Revision ID: 90005fb1996e
Revises: cf34432da220
Create Date: 2026-08-17 11:46:45.978161

Hand-adjusted after autogeneration, which is what alembic's own "please
adjust!" comment is asking for.

Autogenerate produced a single ALTER adding hashed_password as NOT NULL with no
default. Against an empty database that works. Against a table that already has
rows it fails, and it was measured failing:

    sqlite3.IntegrityError: NOT NULL constraint failed: _alembic_tmp_users.hashed_password

Adding a required column to a populated table is always three steps: add it
nullable, backfill every row, then apply the constraint. Doing it in one is the
most common way a migration passes locally and takes production down.

The backfill value matters too. Existing users have no password, so they are
given "!" - a string no bcrypt hash can ever equal, since a real one starts
with $2b$. Every legacy account therefore cannot log in until it resets, which
is the correct outcome. Backfilling a real hash of a known value would give
every legacy account the same working password.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "90005fb1996e"
down_revision: Union[str, Sequence[str], None] = "cf34432da220"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match app.security.UNUSABLE_PASSWORD. Duplicated as a literal on purpose:
# a migration is a historical record and has to keep working even if the
# application constant is later changed or removed.
UNUSABLE_PASSWORD = "!"


def upgrade() -> None:
    """Add the authentication columns, safely for existing rows."""
    # Step 1: add the columns. hashed_password is nullable for now; the other
    # two carry server defaults, so they need no separate backfill.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("hashed_password", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("role", sa.String(length=16), server_default="user", nullable=False)
        )
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False)
        )
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)

    # Step 2: backfill. Any pre-existing user gets a hash that cannot match.
    op.execute(
        sa.text("UPDATE users SET hashed_password = :value WHERE hashed_password IS NULL").bindparams(
            value=UNUSABLE_PASSWORD
        )
    )

    # Step 3: now that no row is null, apply the constraint.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("hashed_password", existing_type=sa.String(length=128), nullable=False)


def downgrade() -> None:
    """Remove the authentication columns."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_role"))
        batch_op.drop_column("is_active")
        batch_op.drop_column("role")
        batch_op.drop_column("hashed_password")
