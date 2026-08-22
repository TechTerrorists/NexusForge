from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


class AgentType(str, enum.Enum):
    LLM = "llm"
    TOOL = "tool"
    HUMAN = "human"
    ORCHESTRATOR = "orchestrator"
    SUBGRAPH = "subgraph"


class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    API_KEY = "api_key"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    IMPORT = "import"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    users: Mapped[list[User]] = relationship("User", back_populates="tenant", lazy="selectin")
    agents: Mapped[list[Agent]] = relationship("Agent", back_populates="tenant", lazy="selectin")
    workflows: Mapped[list[Workflow]] = relationship("Workflow", back_populates="tenant", lazy="selectin")
    knowledge_bases: Mapped[list[KnowledgeBase]] = relationship(
        "KnowledgeBase", back_populates="tenant", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_tenants_slug", "slug"),
        Index("ix_tenants_is_active", "is_active"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users")
    audit_logs: Mapped[list[AuditLog]] = relationship("AuditLog", back_populates="user", lazy="noload")

    __table_args__ = (
        Index("ix_users_tenant_email", "tenant_id", "email", unique=True),
        Index("ix_users_role", "role"),
    )


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_type: Mapped[AgentType] = mapped_column(Enum(AgentType), default=AgentType.LLM)
    model_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tools: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    skills: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="agents")
    created_by_user: Mapped[Optional[User]] = relationship("User", lazy="selectin")
    executions: Mapped[list[AgentExecution]] = relationship(
        "AgentExecution", back_populates="agent", lazy="noload"
    )
    skills_assoc: Mapped[list[Skill]] = relationship(
        "Skill", secondary="agent_skills", back_populates="agents", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_agents_tenant_name", "tenant_id", "name"),
        Index("ix_agents_agent_type", "agent_type"),
    )


class AgentSkills(Base):
    __tablename__ = "agent_skills"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skill_type: Mapped[str] = mapped_column(String(50), default="general")
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    agents: Mapped[list[Agent]] = relationship(
        "Agent", secondary="agent_skills", back_populates="skills_assoc", lazy="noload"
    )


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.DRAFT)
    graph_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    agents: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    edges: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="workflows")
    created_by_user: Mapped[Optional[User]] = relationship("User", lazy="selectin")
    runs: Mapped[list[WorkflowRun]] = relationship(
        "WorkflowRun", back_populates="workflow", lazy="noload"
    )

    __table_args__ = (
        Index("ix_workflows_tenant_status", "tenant_id", "status"),
        Index("ix_workflows_tenant_name", "tenant_id", "name"),
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus), default=ExecutionStatus.PENDING
    )
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="runs")
    agent_executions: Mapped[list[AgentExecution]] = relationship(
        "AgentExecution", back_populates="workflow_run", lazy="noload"
    )

    __table_args__ = (
        Index("ix_workflow_runs_workflow_status", "workflow_id", "status"),
        Index("ix_workflow_runs_created_at", "created_at"),
    )


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus), default=ExecutionStatus.PENDING
    )
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    agent: Mapped[Agent] = relationship("Agent", back_populates="executions")
    workflow_run: Mapped[Optional[WorkflowRun]] = relationship(
        "WorkflowRun", back_populates="agent_executions"
    )

    __table_args__ = (
        Index("ix_agent_executions_agent_status", "agent_id", "status"),
        Index("ix_agent_executions_workflow_run", "workflow_run_id"),
        Index("ix_agent_executions_created_at", "created_at"),
    )


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), default="text-embedding-3-small")
    chunk_size: Mapped[int] = mapped_column(Integer, default=512)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="knowledge_bases")

    __table_args__ = (
        Index("ix_knowledge_bases_tenant_name", "tenant_id", "name"),
    )


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_type: Mapped[str] = mapped_column(String(50), default="function")
    schema_: Mapped[Optional[dict]] = mapped_column("schema", JSONB, default=dict)
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    auth_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    rate_limit: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_tool_definitions_tool_type", "tool_type"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.LOW)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[Optional[User]] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_risk_level", "risk_level"),
    )


class ChangeLog(Base):
    __tablename__ = "change_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_change_logs_entity", "entity_type", "entity_id"),
        Index("ix_change_logs_changed_by", "changed_by"),
        Index("ix_change_logs_created_at", "created_at"),
    )
