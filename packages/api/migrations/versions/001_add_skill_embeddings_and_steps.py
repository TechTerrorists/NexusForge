"""Add skill embeddings, expanded task step fields, and agent communication support.

Revision ID: 001
Revises:
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
    has_vector = True
except ImportError:
    has_vector = False

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if has_vector:
        op.add_column("skill_versions", sa.Column("embedding", Vector(1536), nullable=True))
        op.execute("CREATE INDEX IF NOT EXISTS ix_skill_versions_embedding ON skill_versions USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    op.add_column("task_steps", sa.Column("nexus_phase", sa.String(50), server_default="build", nullable=False))
    op.add_column("task_steps", sa.Column("role", sa.String(255), server_default="", nullable=False))
    op.add_column("task_steps", sa.Column("parallel_group", sa.String(255), nullable=True))
    op.add_column("task_steps", sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False))
    op.add_column("task_steps", sa.Column("acceptance_criteria", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("task_steps", "acceptance_criteria")
    op.drop_column("task_steps", "max_retries")
    op.drop_column("task_steps", "parallel_group")
    op.drop_column("task_steps", "role")
    op.drop_column("task_steps", "nexus_phase")

    if has_vector:
        op.execute("DROP INDEX IF EXISTS ix_skill_versions_embedding")
        op.drop_column("skill_versions", "embedding")
