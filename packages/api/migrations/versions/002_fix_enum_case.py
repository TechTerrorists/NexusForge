"""Compatibility marker for prototype enum normalization.

Revision ID: 002
Revises: 001
"""

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enum values are defined explicitly through SQLAlchemy's values_callable.
    # Existing development databases were already normalized manually.
    return None


def downgrade() -> None:
    return None
