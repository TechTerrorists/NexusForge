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
down_revision = "000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    skill_columns = {column["name"] for column in inspector.get_columns("skill_versions")}
    step_columns = {column["name"] for column in inspector.get_columns("task_steps")}

    if has_vector and "embedding" not in skill_columns:
        op.add_column("skill_versions", sa.Column("embedding", Vector(1536), nullable=True))
        op.execute("CREATE INDEX IF NOT EXISTS ix_skill_versions_embedding ON skill_versions USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    additions = {
        "nexus_phase": sa.Column("nexus_phase", sa.String(50), server_default="build", nullable=False),
        "role": sa.Column("role", sa.String(255), server_default="", nullable=False),
        "parallel_group": sa.Column("parallel_group", sa.String(255), nullable=True),
        "max_retries": sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        "acceptance_criteria": sa.Column("acceptance_criteria", sa.Text(), server_default="", nullable=False),
    }
    for name, column in additions.items():
        if name not in step_columns:
            op.add_column("task_steps", column)


def downgrade() -> None:
    op.drop_column("task_steps", "acceptance_criteria")
    op.drop_column("task_steps", "max_retries")
    op.drop_column("task_steps", "parallel_group")
    op.drop_column("task_steps", "role")
    op.drop_column("task_steps", "nexus_phase")

    if has_vector:
        op.execute("DROP INDEX IF EXISTS ix_skill_versions_embedding")
        op.drop_column("skill_versions", "embedding")
