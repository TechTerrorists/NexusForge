"""Add the durable execution, workforce, and automation kernel.

Revision ID: 003
Revises: 002
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base
from app import models  # noqa: F401


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


NEW_EXECUTION_STATUSES = (
    "planning",
    "queued",
    "blocked",
    "awaiting_input",
    "awaiting_review",
    "changes_requested",
    "merging",
)


def _add_column(table: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    for value in NEW_EXECUTION_STATUSES:
        op.execute(f"ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS '{value}'")

    # Create all newly introduced tables while leaving prototype tables intact.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)

    _add_column("repositories", sa.Column("managed_path", sa.String(1024), nullable=True))
    _add_column("task_plans", sa.Column("constraints", JSONB(), server_default="{}", nullable=False))
    _add_column("task_plans", sa.Column("limits", JSONB(), server_default="{}", nullable=False))
    _add_column("task_steps", sa.Column("role_template_version_id", UUID(as_uuid=True), nullable=True))
    _add_column("task_steps", sa.Column("expected_artifacts", JSONB(), server_default="[]", nullable=False))
    _add_column("task_steps", sa.Column("tool_grants", JSONB(), server_default="[]", nullable=False))
    _add_column("task_steps", sa.Column("side_effect_class", sa.String(50), server_default="workspace", nullable=False))
    _add_column("task_steps", sa.Column("delegation_depth", sa.Integer(), server_default="0", nullable=False))
    _add_column("workflow_runs", sa.Column("workflow_version_id", UUID(as_uuid=True), nullable=True))
    _add_column("workflow_runs", sa.Column("trace_id", sa.String(64), server_default="", nullable=False))
    _add_column("workflow_runs", sa.Column("run_kind", sa.String(32), server_default="agentic_task", nullable=False))
    _add_column("workflow_runs", sa.Column("idempotency_key", sa.String(255), nullable=True))
    _add_column("run_events", sa.Column("trace_id", sa.String(64), server_default="", nullable=False))
    _add_column("run_events", sa.Column("agent_instance_id", UUID(as_uuid=True), nullable=True))
    _add_column("run_events", sa.Column("task_step_id", UUID(as_uuid=True), nullable=True))
    _add_column("run_events", sa.Column("visibility", sa.String(32), server_default="user", nullable=False))
    _add_column("tool_definitions", sa.Column("permission_policy", JSONB(), server_default="{}", nullable=False))
    _add_column("tool_definitions", sa.Column("tenant_id", UUID(as_uuid=True), nullable=True))

    # Prototype tool names were globally unique, which prevented two tenants
    # from defining the same integration. New catalogs are tenant-scoped.
    op.execute("ALTER TABLE tool_definitions DROP CONSTRAINT IF EXISTS uq_tool_definitions_name")
    op.execute("ALTER TABLE tool_definitions DROP CONSTRAINT IF EXISTS tool_definitions_name_key")
    op.execute("DROP INDEX IF EXISTS ix_tool_definitions_name")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tool_definitions_tenant_name ON tool_definitions (tenant_id, name)")
    op.execute("DROP INDEX IF EXISTS ix_role_templates_slug_version")
    op.execute("CREATE UNIQUE INDEX ix_role_templates_slug_version ON role_template_versions (tenant_id, slug, version)")
    op.execute("DROP INDEX IF EXISTS ix_skill_definitions_slug_version")
    op.execute("CREATE UNIQUE INDEX ix_skill_definitions_slug_version ON skill_definition_versions (tenant_id, slug, version)")


def downgrade() -> None:
    for table in (
        "workflow_node_runs",
        "workflow_triggers",
        "workflow_versions",
        "execution_jobs",
        "delegation_requests",
        "agent_messages",
        "agent_instances",
        "role_template_versions",
        "skill_definition_versions",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
