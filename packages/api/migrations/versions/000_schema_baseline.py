"""Create the NexusForge schema baseline.

Revision ID: 000
Revises:
Create Date: 2026-08-27

The early prototype used ``metadata.create_all`` at application startup and
therefore never had a reproducible initial migration.  This baseline is
intentionally idempotent so it can stamp an existing development database as
well as create a fresh one.
"""

from alembic import op

from app.database import Base
from app import models  # noqa: F401


revision = "000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
