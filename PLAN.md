# NexusForge — AI-Powered Enterprise Multi-Agent Workflow Orchestration Platform

## Platform Vision

A production-grade, enterprise-ready multi-agent orchestration platform that combines
agentic reasoning (LangGraph) with deterministic workflows, a visual graph editor,
defense-in-depth security, and a marketplace for agents/skills/workflows — all with
multi-tenancy, observability, and cloud-native deployment.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       Frontend (Next.js 14+)                             │
│  React Flow Graph Editor | ChatKit | Dashboard | Marketplace | Admin     │
│  TUI/Chat Dual-Mode with Durable Handoff                                │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │ REST + SSE + WebSocket
┌────────────────────────────────▼─────────────────────────────────────────┐
│                       API Layer (FastAPI)                                 │
│  Multi-Listener: Loopback (local) + LAN (mobile, authenticated)          │
│  Auth/JWT | RBAC | Rate Limit | Audit | PII Guard | Prompt Guard        │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────────┐
│                     Orchestration Engine                                  │
│  ┌───────────────┐  ┌─────────────────┐  ┌─────────────────────────┐   │
│  │ LangGraph      │  │ Deterministic   │  │ Middleware Pipeline      │   │
│  │ StateGraph     │  │ Workflows       │  │ beforeAgent > afterAgent│   │
│  │ (agentic)      │  │ (if/loop/seq)   │  │ wrapModel | wrapTool    │   │
│  └───────┬───────┘  └────────┬────────┘  └─────────────────────────┘   │
│          └──────┬────────────┘                                          │
│     Supervisor / Router                                                 │
│     Agent Switching Saga (mid-session LLM/agent replacement)            │
└──────────┬──────┬──────────────────────────────────────────────────────┘
           │      │
   ┌───────▼──┐ ┌─▼───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐
   │ Agents   │ │ Tool Server  │ │ Knowledge │ │ Handoff   │ │ Skills   │
   │ (skills, │ │ (MCP, 14+   │ │ (RAG,     │ │ (Bull     │ │ (SKILL.md│
   │  tools)  │ │  connectors)│ │ GraphRAG) │ │  queues)  │ │ protocols│
   └──────────┘ └──────┬──────┘ └───────────┘ └───────────┘ └──────────┘
                       │
              ┌────────▼──────────────────────────────────────┐
              │         Secure Reviewer Gateway                │
              │  (sandboxed template validation)               │
              └────────┬──────────────────────────────────────┘
                       │
   ┌───────────────────▼──────────────────────────────────────────────┐
   │                Data & State Layer                                  │
   │  PostgreSQL+pgvector | Redis | Object Storage                     │
   │  (checkpoints, audit, memory, tenants, sessions)                  │
   │  CDC Pipeline (DB-triggered events for lightweight deployment)    │
   └──────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | Python 3.12+, LangGraph, FastAPI, SQLAlchemy, Alembic | Strong LangGraph ecosystem, async-first, type-safe |
| **Frontend** | Next.js 14+, React 19, TypeScript, React Flow, Tailwind CSS | Server components, visual graph editor, shadcn/ui |
| **Database** | PostgreSQL 16 + pgvector | Checkpoints, audit, memory, vector search |
| **Cache/Queues** | Redis (Streams, Pub/Sub, Bull queues) | Event-driven, handoff queues, SSE broadcasting |
| **Observability** | OpenTelemetry, Prometheus, LangSmith/Langfuse | Distributed tracing, metrics, LLM observability |
| **Deployment** | Docker Compose + Kubernetes manifests | Local dev/small to production scale |

---

## Inspiration Sources

| Project | Key Patterns Adopted |
|---|---|
| **agency-agents/** | Personality-driven agent definitions, NEXUS orchestration doctrine, tool-agnostic format |
| **ForgeFlow/** | Hub-and-spoke supervisor, defense-in-depth security, budget guard, circuit breaker, enterprise connectors |
| **xpert/** | Agent-workflow hybrid, middleware lifecycle hooks, per-agent state channels, handoff routing |
| **agent-framework/** | 5 orchestration patterns, A2A/AG-UI/MCP protocols, skills progressive disclosure, harness agent |
| **agent-orchestrator/** | Durable facts + derived status, agent switching saga, TUI/chat dual-mode handoff, CDC pipeline, secure reviewer gateway |

---

## Phase 1: Foundation (Weeks 1-3)

### 1.1 Project Structure

```
nexusforge/
  packages/
    api/                         # FastAPI application
      app/
        main.py                  # FastAPI app factory, middleware stack
        config.py                # Pydantic Settings (env-based)
        deps.py                  # Dependency injection
        routers/                 # 10+ API routers
        middleware/               # Security, RBAC, rate limit, audit, PII
        auth/                    # JWT, Argon2, TOTP MFA, OIDC SSO
      migrations/                # Alembic
      tests/

    orchestration/               # Core orchestration engine
      graph/                     # LangGraph StateGraph builder
      workflows/                 # Deterministic workflow nodes
      state/                     # WorkflowState TypedDict
      supervisor/                # Supervisor router (structured output)
      switching/                 # Agent Switching Saga
      patterns/                  # Sequential, Concurrent, Handoff, Group, Magentic

    agents/                      # Agent definitions and runtime
      base.py                    # BaseAgent with circuit breaker
      registry.py                # Agent registry + capability discovery
      session.py                 # AgentSession with pluggable persistence
      context.py                 # AgentRunContext (AsyncLocal ambient)
      factory.py                 # AgentFactory (YAML/JSON declarative)
      types/                     # Agent type definitions

    middleware/                   # Middleware pipeline
      pipeline.py                # beforeAgent -> afterAgent lifecycle
      builtins/                  # BudgetGuard, PromptInjection, PII, etc.
      registry.py                # Middleware registry

    connectors/                  # Enterprise connectors
      base.py                    # BaseConnector with retry, SSRF guard
      hubspot/
      salesforce/
      jira/
      github/
      slack/
      servicenow/
      sap/
      microsoft_graph/

    knowledge/                   # RAG system
      vector_store.py            # pgvector embeddings
      graph_rag.py               # Graph-based retrieval
      hybrid.py                  # Vector + graph hybrid
      file_understanding.py      # PDF extraction, chunking, citations

    security/                    # Defense-in-depth security
      pii_redactor.py            # Regex PII scrubbing
      prompt_guard.py            # Heuristic injection detection
      ssrf_guard.py              # DNS pinning, private IP blocking
      tool_quarantine.py         # <UNTRUSTED_TOOL_OUTPUT> envelope
      email_allowlist.py         # Outbound email pinning
      rbac.py                    # Role-based access control

    memory/                      # Memory and state
      store.py                   # pgvector semantic store
      session_store.py           # Conversation persistence
      durable_facts.py           # Durable facts + derived status

    skills/                      # Skills system
      registry.py                # Skill discovery + registration
      progressive.py             # Advertise -> Load -> Execute
      sources/                   # File, inline, class, MCP-based
      security.py                # Symlink/path-traversal protection

    handoff/                     # Inter-agent communication
      dispatcher.py              # Message routing
      queues.py                  # Queue management (realtime/batch/integration)
      cancellation.py            # Cooperative AbortSignal propagation

    observability/               # Observability stack
      tracing.py                 # OpenTelemetry auto-instrumentation
      metrics.py                 # Prometheus /metrics endpoint
      cost_tracker.py            # tiktoken token counting + cost table
      evaluation.py              # LLM-as-judge (faithfulness, relevance, coherence)
      audit.py                   # Immutable audit log

    marketplace/                 # Template marketplace
      registry.py                # manifest.yaml schema + validation
      installer.py               # One-click install with dependency resolution
      sandbox.py                 # Secure reviewer gateway for community templates

    cdc/                         # Change Data Capture (lightweight events)
      poller.py                  # DB trigger -> change_log -> poller
      broadcaster.py             # Fan-out to SSE, WebSocket, cache

    browser/                     # Per-worker browser isolation
      isolation.py               # Isolated browser profiles per session
      cdp.py                     # CDP automation bridge

    packages/web/                # Next.js frontend
      src/
        app/                     # App router pages
        components/
          graph-editor/          # React Flow graph editor
          chatkit/               # Embeddable chat component
          dashboard/             # Dashboard views
          marketplace/           # Template browser
          ui/                    # shadcn/ui primitives
        hooks/                   # React hooks
        stores/                  # Zustand state management
        lib/                     # API client (openapi-fetch)
      package.json

    docker/
      docker-compose.yml         # Full stack
      docker-compose.dev.yml     # Development overrides
      Dockerfile.*

    k8s/                         # Kubernetes manifests
      base/
      overlays/

    .github/workflows/           # CI/CD
    pyproject.toml               # Python workspace config
    README.md
```

### 1.2 Core Data Models

```python
from uuid import UUID
from datetime import datetime
from sqlalchemy import JSON, ForeignKey, String, Integer, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

class Base(DeclarativeBase):
    pass

# Durable Facts pattern (from agent-orchestrator)
# Status is NEVER stored - derived at read time from minimal facts

class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))
    thread_id: Mapped[str]              # LangGraph thread for resumption
    workflow_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)

    # Durable facts only
    activity_state: Mapped[str]         # "idle" | "running" | "blocked" | "waiting_human"
    is_terminated: Mapped[bool] = mapped_column(default=False)
    last_heartbeat: Mapped[datetime]
    error_count: Mapped[int] = mapped_column(default=0)
    cost_cents: Mapped[int] = mapped_column(default=0)
    tokens_used: Mapped[int] = mapped_column(default=0)

    # Conversation state
    state_json: Mapped[dict] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey("workflows.id"))

    # Durable facts
    activity_state: Mapped[str]         # "planning" | "executing" | "awaiting_approval" | "completed"
    is_terminated: Mapped[bool] = mapped_column(default=False)
    current_node: Mapped[str | None]    # Which node is active
    last_heartbeat: Mapped[datetime]
    total_cost_cents: Mapped[int] = mapped_column(default=0)

    state_json: Mapped[dict] = mapped_column(JSON)
    checkpoint_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024))
    prompt: Mapped[str]                 # System prompt
    personality: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # vibe, communication_style, critical_rules

    model_provider: Mapped[str]         # openai | anthropic | ollama | azure
    model_name: Mapped[str]             # gpt-4o | claude-sonnet-4-20250514 | etc
    model_config: Mapped[dict] = mapped_column(JSON)  # temperature, max_tokens, etc

    tools: Mapped[dict] = mapped_column(JSON)          # List of tool definitions
    knowledge_bases: Mapped[dict] = mapped_column(JSON) # List of KB IDs
    middleware: Mapped[dict] = mapped_column(JSON)      # List of middleware configs
    skills: Mapped[dict] = mapped_column(JSON)          # List of skill IDs

    graph_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024))
    domain: Mapped[str]                 # sales_ops | support_ops | finance_recon | custom
    version: Mapped[int] = mapped_column(default=1)
    manifest_json: Mapped[dict] = mapped_column(JSON)

    graph_json: Mapped[dict] = mapped_column(JSON)     # Nodes + edges (React Flow compatible)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    embedding_model: Mapped[str] = mapped_column(String(128))
    chunk_config: Mapped[dict] = mapped_column(JSON)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024))
    schema_json: Mapped[dict] = mapped_column(JSON)
    connector_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1024))
    protocol_json: Mapped[dict] = mapped_column(JSON)
    source_type: Mapped[str]            # file | inline | class | mcp
    source_content: Mapped[str]         # SKILL.md content or code
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str]                   # free | pro | enterprise
    config_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[str]                   # admin | manager | developer | viewer | anonymous | service
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    tenant_id: Mapped[UUID | None] = mapped_column(nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(1024))
    status_code: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str]                # success | failure | blocked
    latency_ms: Mapped[float] = mapped_column(Float)
    client_ip: Mapped[str] = mapped_column(String(45))
    request_body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128))
    record_id: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str]              # INSERT | UPDATE | DELETE
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

### 1.3 Derived Status Pattern

```python
# Status is computed at read time, never stored
# From agent-orchestrator's durable facts pattern

from datetime import datetime, timedelta

def derive_execution_status(execution: AgentExecution) -> str:
    """Derive display status from durable facts."""
    if execution.is_terminated:
        if execution.error_count > 0:
            return "failed"
        return "completed"

    if execution.activity_state == "blocked":
        if needs_human_input(execution):
            return "awaiting_approval"
        return "blocked"

    if execution.activity_state == "running":
        if is_stale(execution.last_heartbeat, threshold_seconds=30):
            return "stale"
        return "running"

    if execution.activity_state == "waiting_human":
        return "awaiting_approval"

    if execution.activity_state == "idle":
        if has_pending_work(execution):
            return "queued"
        return "idle"

    return "unknown"


def derive_workflow_status(run: WorkflowRun) -> str:
    """Derive workflow status from durable facts."""
    if run.is_terminated:
        return "completed" if run.error_count == 0 else "failed"

    if run.activity_state == "awaiting_approval":
        return "awaiting_approval"

    if run.activity_state == "executing":
        if is_stale(run.last_heartbeat):
            return "stale"
        return "running"

    if run.activity_state == "planning":
        return "planning"

    return "unknown"


def is_stale(heartbeat: datetime, threshold_seconds: int = 30) -> bool:
    """Check if a heartbeat is stale."""
    return (datetime.utcnow() - heartbeat) > timedelta(seconds=threshold_seconds)
```

---

## Phase 2: Orchestration Engine (Weeks 3-5)

### 2.1 Hybrid Workflow Engine

**LangGraph StateGraph (agentic mode):**
- Supervisor agent routes via `RoutingDecision` (structured output, never calls tools)
- Hub-and-spoke: all workers return to supervisor
- PostgreSQL checkpointing for crash recovery
- `interrupt_before` for human-in-the-loop
- `thread_id` as resumption key

**Deterministic Workflow Nodes:**
- Start, End, If/Else, Iterator, Assigner (variable ops), HTTP, Subflow, Code (Python/JS), Classifier, Template, Task

**Graph Compilation:**
- `WorkflowBuilder` - fluent API for building workflow graphs
- Per-graph node closures (prevents shared state bugs)
- `StateAnnotation` with per-agent channels (`agent_<key>` namespaces)

### 2.2 State Management

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class SystemContext(TypedDict):
    language: str
    timezone: str
    date: str
    thread_id: str
    workspace_paths: list[str]

class HumanContext(TypedDict):
    input: str | None
    approval_token: str | None

class WorkflowState(TypedDict):
    # Shared channels
    messages: Annotated[list[BaseMessage], add_messages]
    input: str
    output: str
    sys: SystemContext
    human: HumanContext
    memories: list[str]
    pending_follow_ups: list[str]

    # Routing (last-write-wins)
    next_agent: str | None
    current_stage: str
    current_node: str | None

# Per-agent channels (dynamically created)
# agent_<key>.messages - per-agent message history
# agent_<key>.output - agent output
# agent_<key>.error - agent error state
# agent_<key>.variables - agent-scoped variables
```

### 2.3 Orchestration Patterns

```python
# Sequential
workflow = (
    WorkflowBuilder()
    .sequential([researcher, analyzer, executor])
    .build()
)

# Concurrent (fan-out/fan-in)
workflow = (
    WorkflowBuilder()
    .concurrent([agent_a, agent_b, agent_c])
    .aggregate(summarizer)
    .build()
)

# Handoff (decentralized routing)
workflow = (
    WorkflowBuilder()
    .handoff(agents=[sales, support, engineering])
    .with_autonomous_mode(max_turns=10)
    .build()
)

# Group Chat
workflow = (
    WorkflowBuilder()
    .group_chat(agents=[analyst, coder, reviewer], manager=orchestrator)
    .build()
)

# Magentic (LLM-powered dynamic planning)
workflow = (
    WorkflowBuilder()
    .magentic(manager=planner, agents=[researcher, coder, tester])
    .with_replan_threshold(0.3)
    .build()
)
```

### 2.4 Agent Switching Saga

```python
from enum import Enum

class SwitchPolicy(Enum):
    DRAIN = "drain"        # Finish current turn, then switch
    INTERRUPT = "interrupt"  # Cancel active turn, switch immediately

class SwitchResult:
    success: bool
    message: str
    new_agent_id: str | None = None

class AgentSwitchingSaga:
    """Durable saga to replace the underlying agent/LLM mid-session.
    From agent-orchestrator."""

    async def execute(
        self,
        session_id: str,
        source_agent_id: str,
        target_agent_id: str,
        policy: SwitchPolicy = SwitchPolicy.DRAIN,
    ) -> SwitchResult:
        """
        1. Validate target agent exists and is compatible
        2. Pause source agent (drain active turn or interrupt)
        3. Snapshot current state (conversation, branch, PR ownership)
        4. Activate target agent with snapshot
        5. Deliver continuation message to target
        6. Verify target is running
        7. Mark source as switched-out
        8. On failure at any step -> rollback to source
        """
        saga = SwitchSaga(session_id, source_agent_id, target_agent_id)

        try:
            await saga.confirm_source_stopping(policy)
            await saga.activate_target()
            await saga.deliver_continuation()
            await saga.verify_target_running()
            await saga.mark_source_switched_out()
            return SwitchResult(success=True, message="Switch completed", new_agent_id=target_agent_id)
        except Exception as e:
            await saga.rollback()
            return SwitchResult(success=False, message=str(e))
```

---

## Phase 3: Visual Graph Editor (Weeks 4-7)

### 3.1 React Flow Graph Editor

- **Node types**: Agent, Tool, Knowledge, Workflow, If/Else, Loop, HTTP, Code, Start, End
- **Edge types**: Sequential, Conditional, Fan-out, Fan-in
- **Configuration panels**: Prompt editor, model selector, tool picker, knowledge base selector, middleware toggles
- **Real-time validation**: Required fields, connection compatibility, cycle detection
- **Canvas**: Zoom/pan, minimap, snap-to-grid, alignment guides
- **Persistence**: Graph JSON saved to `Workflow.graph_json`, compatible with React Flow's `toObject()`

### 3.2 TUI/Chat Dual-Mode Handoff

```python
from enum import Enum

class SessionMode(Enum):
    GRAPH = "graph"    # Visual graph editor view
    CHAT = "chat"      # Chat/conversation view

class HandoffPolicy(Enum):
    DRAIN = "drain"        # Finish current turn before switching
    INTERRUPT = "interrupt"  # Cancel active turn, switch immediately

class HandoffResult:
    success: bool
    from_mode: SessionMode
    to_mode: SessionMode
    message: str

class InterfaceHandoffManager:
    """Durable handoff between graph editor view and chat view.
    From agent-orchestrator."""

    async def handoff(
        self,
        session_id: str,
        from_mode: SessionMode,
        to_mode: SessionMode,
        policy: HandoffPolicy = HandoffPolicy.DRAIN,
    ) -> HandoffResult:
        """
        1. Acquire transition lock (generation fencing)
        2. Drain active controller (finish current turn or cancel)
        3. Save controller state (conversation, cursors, selection)
        4. Create transition outbox (messages arriving during transition)
        5. Initialize target controller with saved state
        6. Flush outbox to new controller
        7. Release transition lock
        8. On failure -> rollback to previous controller
        """
        pass  # Implementation in Phase 3
```

### 3.3 Dashboard Views

| View | Description |
|---|---|
| **Overview** | Active workflows, recent runs, system health, cost summary |
| **Live Runs** | Real-time workflow execution with node highlighting, agent reasoning stream |
| **Agents** | Agent registry, capabilities, health status, run history |
| **Tools** | Tool marketplace, connector configs, MCP server status |
| **Knowledge** | Knowledge base management, RAG configuration, chunk stats |
| **Approvals** | Pending human approvals with approve/reject, escalation status |
| **Audit** | Immutable audit log viewer with filters |
| **Cost** | Per-agent, per-workflow cost breakdowns, budget alerts |
| **Marketplace** | Workflow templates, agent definitions, skills |
| **Settings** | Tenant config, RBAC, API keys, model provider settings |

---

## Phase 4: Enterprise Connectors and Tools (Weeks 6-8)

### 4.1 MCP Tool Server

- FastMCP server on separate port (`:8001`)
- 14+ tool routers with type-safe schemas
- Tool-output quarantine (`<UNTRUSTED_TOOL_OUTPUT>` envelope)
- SSRF guard with DNS pinning on all outbound URLs

### 4.2 Enterprise Connectors

All inherit `BaseConnector` with:
- Retry-with-backoff on 429/502/503/504 with full jitter
- `Retry-After` header respect
- SSRF guard on every outbound URL
- `RetryableError` vs `PermanentError` for workflow branching
- Mock responses when credentials absent (`is_enabled` pattern)

| Connector | Capability |
|---|---|
| HubSpot | Upsert contacts, idempotent deals, notes |
| Salesforce | Leads + opportunities + SOQL |
| Jira Cloud | Issue create + transitions |
| ServiceNow | Table API incidents + change requests |
| GitHub | Issues, PRs, releases, repo metadata |
| Slack | Messages, channels, approval cards |
| Microsoft Graph | Teams / Outlook / Calendar |
| SAP S/4HANA | OData v2 + CSRF for orders + invoices |

### 4.3 Knowledge and RAG

- Vector store: pgvector cosine similarity, namespace-scoped, TTL
- GraphRAG: Entity/community top-K, neighbor hops, hybrid vector+graph
- Multi-level filtering: fixed (agent-owned) + agent-authored filter nodes
- File understanding: PDF text extraction, chunking, citation anchors

### 4.4 Per-Worker Browser Isolation

```python
from dataclasses import dataclass

@dataclass
class BrowserProfile:
    session_id: str
    profile_dir: str
    cdp_socket_path: str

class BrowserIsolationManager:
    """Each worker session gets an isolated browser profile.
    From agent-orchestrator."""

    async def create_profile(self, session_id: str) -> BrowserProfile:
        """
        - Create isolated Chrome profile directory
        - Separate cookies, web storage, cache
        - CDP automation via dedicated local socket
        - Network capture scoped to session, auto-expires
        """
        pass  # Implementation in Phase 4

    async def get_cdp_connection(self, session_id: str):
        """Route CDP commands only to the selected session's browser."""
        pass

    async def destroy_profile(self, session_id: str) -> None:
        """Clean up profile on session termination."""
        pass
```

### 4.5 Secure Reviewer Gateway

```python
from dataclasses import dataclass

@dataclass
class ValidationResult:
    passed: bool
    errors: list[str]
    warnings: list[str]
    score: float  # 0.0 - 1.0

class ReviewerGateway:
    """Capability-gated boundary for untrusted reviewer CLIs / marketplace templates.
    From agent-orchestrator."""

    async def validate_template(
        self,
        template_manifest: dict,
        reviewer_config: dict,
    ) -> ValidationResult:
        """
        1. Run in neutral working directory (never the main checkout)
        2. Content-addressed task manifest
        3. Structured source access (pinned-tree reads, bounded search)
        4. Structured side effects (post review only to manifest target)
        5. Platform sandboxing (container or nsjail)
        6. Timeout enforcement
        7. Return structured validation result
        """
        pass  # Implementation in Phase 4
```

---

## Phase 5: Security and Observability (Weeks 7-9)

### 5.1 Defense-in-Depth Security

Five middleware layers in specific order:

```python
# Request flow:
# SecurityHeaders -> RBAC -> RateLimit -> Security (PII + prompt guard) -> Audit -> Handler

class SecurityHeadersMiddleware:
    """Hardening headers on every response."""
    pass

class RBACMiddleware:
    """JWT verification + role-based permission (fail-closed on unmapped routes)."""
    pass

class RateLimitMiddleware:
    """Token-bucket, tiered: anon 10/min, mutating 30/min, read 120/min."""
    pass

class SecurityMiddleware:
    """PII redaction + prompt-injection scanning of every JSON body."""
    pass

class AuditMiddleware:
    """Immutable log of every request/response with user, role, outcome, latency."""
    pass
```

**RBAC Roles:**
- `admin` - full access
- `manager` - approve workflows, manage agents
- `developer` - create/edit agents and workflows
- `viewer` - read-only
- `anonymous` - public marketplace browsing
- `service` - API key access for integrations

**PII Redactor:** Conservative regex scrubbing at API edge (SSN, email, phone, credit card, AWS keys)

**Prompt Injection Guard:** Heuristic risk scoring (LOW/MEDIUM/HIGH), blocks HIGH at HTTP 400

**SSRF Guard:** Blocks private IPs, IMDS, non-http(s) schemes; DNS pinning to defeat rebinding

**Tool Output Quarantine:** Wraps results in `<UNTRUSTED_TOOL_OUTPUT>` envelope + system prompt instruction

**Email Allowlist:** Pins outbound recipients so LLM cannot exfiltrate

### 5.2 Observability

- **OpenTelemetry** distributed tracing (auto-instrumented FastAPI + LangGraph)
- **Prometheus** `/metrics` endpoint
- **Cost tracking**: tiktoken-based token counting, per-model cost table, per-agent breakdown
- **Budget guard**: halts workflow before projected spend exceeds `BUDGET_LIMIT_USD`
- **Evaluation**: LLM-as-judge (faithfulness, relevance, coherence, hallucination detection)

### 5.3 Resilience

- **Circuit breaker**: per-agent CLOSED/OPEN/HALF_OPEN (5 failures, 30s recovery)
- **Budget guard**: pre-call cost projection check
- **Retry with exponential backoff + jitter** on all external calls
- **Graceful degradation**: connectors return mock responses when credentials absent
- **Container reaping**: multi-condition termination guardrails - only terminate when runtime AND process are both dead, no recent activity contradicts that

### 5.4 Multi-Listener Security

```python
# From agent-orchestrator - loopback vs LAN listeners
#
# Listener 1: Loopback (127.0.0.1) - unauthenticated, for local app and CLI
# Listener 2: LAN (0.0.0.0) - opt-in, bearer-password authenticated, for mobile
#
# Per-source lockout, rotating passwords, QR-code pairing for mobile
```

---

## Phase 6: Skills and Marketplace (Weeks 8-10)

### 6.1 Skills System

Progressive disclosure pattern from agent-framework:

```python
from dataclasses import dataclass

@dataclass
class SkillStep:
    name: str
    description: str
    required_tools: list[str]
    output_schema: dict

@dataclass
class SkillProtocol:
    """Structured SKILL.md protocol that agents follow."""
    name: str
    description: str
    steps: list[SkillStep]
    required_tools: list[str]
    output_schema: dict

# Pipeline: Advertise -> Load -> Read Resources -> Run Scripts
# Sources: File (SKILL.md), inline (code), class-based, MCP-based
# Security: symlink/path-traversal protection, trust boundaries
```

### 6.2 Marketplace

- `manifest.yaml` schema for workflow/agent template definitions
- Division-based organization (engineering, design, marketing, etc.)
- One-click install with dependency resolution
- Version management and compatibility checks
- Community templates validated through Secure Reviewer Gateway

### 6.3 Declarative Agent Definitions

```yaml
# YAML/JSON agent definitions with personality
name: Frontend Developer
description: Expert frontend developer specializing in modern web technologies
color: cyan
emoji: "🖥️"
vibe: Builds responsive, accessible web apps with pixel-perfect precision

personality:
  communication_style: Concise, uses code examples, references design systems
  critical_rules:
    - Always use TypeScript
    - Never use inline styles
    - Test all components

model:
  provider: openai
  name: gpt-4o
  temperature: 0.7

tools:
  - react_flow_graph_builder
  - code_editor
  - browser_automation

knowledge_bases:
  - design_system_docs
  - component_library

middleware:
  - structured_output
  - budget_guard:
      limit_usd: 5.00
```

---

## Phase 7: Multi-Tenancy and Deployment (Weeks 9-11)

### 7.1 Multi-Tenancy

- Tenant isolation via `tenant_id` on all data models
- Per-tenant configuration (LLM providers, limits, features)
- RBAC with tenant-scoped roles
- Session store with isolation-key scoping

### 7.2 Docker Compose Deployment

```yaml
services:
  api:
    build: ./packages/api
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://nexusforge:secret@postgres:5432/nexusforge
      REDIS_URL: redis://redis:6379/0

  webapp:
    build: ./packages/web
    ports: ["3000:3000"]
    depends_on: [api]

  postgres:
    image: pgvector/pgvector:pg16
    volumes: ["pgdata:/var/lib/postgresql/data"]
    environment:
      POSTGRES_DB: nexusforge
      POSTGRES_USER: nexusforge
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    volumes: ["redisdata:/data"]

  mcp_server:
    build: ./packages/api
    command: ["python", "-m", "nexusforge.mcp_server"]
    ports: ["8001:8001"]
    depends_on: [api]

volumes:
  pgdata:
  redisdata:
```

### 7.3 Kubernetes Manifests

- **StatefulSet** for PostgreSQL (with PVC)
- **Deployments** for API, WebApp, MCP Server
- **HPAs** for API and MCP Server (CPU + custom metrics)
- **NetworkPolicies** for inter-service communication
- **Ingress** for external access with TLS termination

### 7.4 CI/CD Pipeline

```yaml
# GitHub Actions
name: CI
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/ruff-action@v3    # Python lint
      - uses: eslint/eslint-action@v1     # TypeScript lint

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: mypy packages/               # Python type check
      - run: tsc --noEmit                  # TypeScript type check

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest packages/              # Python tests
      - run: vitest run packages/web/      # TypeScript tests

  build:
    needs: [lint, typecheck, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t nexusforge-api ./packages/api
      - run: docker build -t nexusforge-web ./packages/web
```

---

## Phase 8: Advanced Features (Weeks 10-12)

### 8.1 Event-Driven Architecture

**Primary: Redis Streams** (for Docker Compose lightweight deployments)
**Optional: Kafka** (for production scale)
**Lightweight alternative: CDC Pipeline** (DB-triggered events, no external broker)

```python
# CDC Pipeline (from agent-orchestrator)
# PostgreSQL triggers write to change_log on every mutation
# CDC Poller tails change_log, decodes events, fans out via Broadcaster
# Subscribers: SSE writers, WebSocket broadcasts, cache invalidation
```

### 8.2 Background Agents

From agent-framework:
- Parent agents delegate work to child agents running concurrently
- Status polling and result retrieval
- Session propagation from parent to child

### 8.3 Real-Time Collaboration

From Xpert's Yjs CRDT system:
- Multi-user graph editing with presence tracking
- Cursor/focus/selection broadcasting
- Materialization pipeline projecting CRDT state to business entities

### 8.4 Evaluation System

From ForgeFlow:
- LLM-as-judge: faithfulness, relevance, coherence, hallucination detection
- Eval regression gate in CI
- Per-workflow evaluation metrics

### 8.5 Structured Skill Protocols

From agent-orchestrator's bug-triage pattern:
- `.agents/skills/<skill-name>/SKILL.md` files
- Step-by-step agent instructions for first-responder protocols
- Tools can follow these protocols autonomously
- Examples: bug triage, incident response, code review, deployment verification

---

## Key Design Principles

| Principle | Source |
|---|---|
| **Supervisor never calls tools** - deterministic, auditable routing | ForgeFlow |
| **Hub-and-spoke** - all workers return to supervisor | ForgeFlow |
| **Tool-output quarantine** - defense against 2nd-order injection | ForgeFlow |
| **Agent-workflow hybrid** - agentic reasoning + deterministic control | Xpert |
| **Per-agent state channels** - namespaced, typed, isolated | Xpert |
| **Middleware lifecycle hooks** - beforeAgent -> afterAgent | Xpert + agent-framework |
| **Progressive disclosure** - tools/skills advertised then loaded on demand | agent-framework |
| **5 orchestration patterns** - sequential, concurrent, handoff, group, magentic | agent-framework |
| **Personality-driven agents** - identity, communication style, vibe | agency-agents |
| **Evidence-over-claims** - quality requires proof, not assertions | agency-agents |
| **Defense-in-depth** - 5 security layers in specific order | ForgeFlow |
| **Circuit breaker per agent** - CLOSED/OPEN/HALF_OPEN | ForgeFlow |
| **Budget guard** - pre-call cost projection | ForgeFlow |
| **YAML-routed handoff** - hot-reloadable message routing | Xpert |
| **Durable facts + derived status** - eliminate status staleness | agent-orchestrator |
| **Agent switching saga** - mid-session LLM/agent replacement | agent-orchestrator |
| **TUI/Chat dual-mode handoff** - durable interface transitions | agent-orchestrator |
| **CDC pipeline** - real-time events without external brokers | agent-orchestrator |
| **Secure reviewer gateway** - sandboxed template validation | agent-orchestrator |
| **Per-worker browser isolation** - isolated browser profiles | agent-orchestrator |

---

## Estimated Timeline

| Phase | Weeks | Key Deliverables |
|---|---|---|
| 1. Foundation | 1-3 | Project structure, data models, agent core, middleware pipeline, derived status |
| 2. Orchestration | 3-5 | LangGraph engine, deterministic workflows, state management, 5 patterns, agent switching |
| 3. Visual Editor | 4-7 | React Flow graph editor, ChatKit, dual-mode handoff, dashboard views |
| 4. Connectors | 6-8 | MCP tool server, 8 enterprise connectors, RAG, browser isolation, reviewer gateway |
| 5. Security & Obs | 7-9 | Security middleware (5 layers), observability, resilience, multi-listener |
| 6. Skills & Market | 8-10 | Skills system, marketplace, declarative agent definitions |
| 7. Deploy | 9-11 | Multi-tenancy, Docker Compose, Kubernetes, CI/CD |
| 8. Advanced | 10-12 | Event-driven (Redis/CDC), background agents, CRDT collaboration, evaluation |

**Total: ~12 weeks** with overlapping phases

---

## File Count Estimate

| Component | Files | Language |
|---|---|---|
| packages/api | ~60 | Python |
| packages/orchestration | ~25 | Python |
| packages/agents | ~15 | Python |
| packages/middleware | ~10 | Python |
| packages/connectors | ~30 | Python |
| packages/knowledge | ~8 | Python |
| packages/security | ~8 | Python |
| packages/memory | ~5 | Python |
| packages/skills | ~8 | Python |
| packages/handoff | ~5 | Python |
| packages/observability | ~8 | Python |
| packages/marketplace | ~5 | Python |
| packages/cdc | ~4 | Python |
| packages/browser | ~4 | Python |
| packages/web | ~80 | TypeScript |
| docker/k8s/ci | ~15 | YAML/Dockerfile |
| **Total** | **~290** | Python + TypeScript |
