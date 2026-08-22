# NexusForge

AI-Powered Enterprise Multi-Agent Workflow Orchestration Platform

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+
- Node.js 20+

### Development Setup

```bash
# Clone and start
cd nexusforge
docker compose -f docker/docker-compose.dev.yml up -d

# API available at http://localhost:8000
# Frontend available at http://localhost:3000
# API docs at http://localhost:8000/docs
```

### Manual Setup (without Docker)

```bash
# Backend
cd packages/api
pip install -e .
uvicorn app.main:app --reload --port 8000

# Frontend
cd packages/web
npm install --legacy-peer-deps
npm run dev
```

## Architecture

```
Frontend (Next.js 14+ / React 19 / React Flow)
    |
    | REST + SSE + WebSocket
    v
API Layer (FastAPI + 5-layer security middleware)
    |
    +---> Orchestration Engine (LangGraph StateGraph + 5 patterns)
    +---> Agents (base, registry, sessions, factory, context)
    +---> Middleware Pipeline (budget guard, PII, prompt guard, structured output, tool approval)
    +---> Connectors (HubSpot, Salesforce, Jira, GitHub, Slack, ServiceNow, SAP, MS Graph)
    +---> Knowledge (pgvector + GraphRAG + hybrid retrieval)
    +---> Security (PII redactor, SSRF guard, prompt guard, tool quarantine, email allowlist)
    +---> Memory (semantic store, session store, durable facts)
    +---> Skills (progressive disclosure, sources, security)
    +---> Handoff (Redis queues, dispatcher, cancellation)
    +---> Observability (OpenTelemetry, Prometheus, cost tracking, evaluation, audit)
    +---> Marketplace (template registry, installer, sandbox)
    +---> CDC (poller, broadcaster)
    +---> Browser (CDP, per-worker isolation)
    |
    v
Data Layer: PostgreSQL 16+pgvector | Redis 7
```

## Project Structure

```
nexusforge/
  pyproject.toml                      # Python workspace config (ruff, mypy)
  README.md
  .github/workflows/ci.yml           # CI/CD pipeline

  packages/
    api/                              # FastAPI application
      pyproject.toml                  # Python deps (hatchling)
      alembic.ini
      app/
        main.py                       # App factory + middleware stack
        config.py                     # Pydantic Settings (env-based)
        database.py                   # SQLAlchemy async engine + session
        deps.py                       # Shared FastAPI dependency helpers
        models.py                     # 12 ORM models
        auth/                         # JWT, password hashing, dependencies
        middleware/                    # 5 security middleware layers
        routers/                      # 10 API routers
      migrations/                     # Alembic migrations

    orchestration/                    # LangGraph orchestration engine
      state.py                        # WorkflowState TypedDict
      graph/                          # StateGraph builder, edges, nodes
      patterns/                       # Sequential, Concurrent, Handoff, Group, Magentic
      supervisor/                     # Hub-and-spoke supervisor router
      switching/                      # Agent Switching Saga
      workflows/                      # Deterministic workflow nodes

    agents/                           # Agent runtime
      base.py                         # BaseAgent with circuit breaker
      registry.py                     # Agent registry + capability discovery
      session.py                      # Pluggable session persistence
      context.py                      # AgentRunContext (AsyncLocal)
      factory.py                      # YAML/JSON declarative agent factory
      types/models.py                 # Agent type definitions

    middleware/                        # Middleware pipeline
      pipeline.py                     # beforeAgent -> afterAgent lifecycle
      registry.py                     # Middleware name->class registry
      builtins/                       # BudgetGuard, PromptGuard, PII, etc.

    connectors/                       # 8 enterprise connectors
      base.py                         # BaseConnector (retry, SSRF guard)
      github/                         # GitHub REST API
      hubspot/                        # HubSpot CRM
      jira/                           # Jira Cloud
      microsoft_graph/                # Teams / Outlook / Calendar
      salesforce/                     # Salesforce CRM
      sap/                            # SAP S/4HANA OData
      servicenow/                     # ServiceNow Table API
      slack/                          # Slack messaging

    knowledge/                        # RAG system
      vector_store.py                 # pgvector cosine similarity
      graph_rag.py                    # Entity/community graph retrieval
      hybrid.py                       # Vector + keyword + graph hybrid
      file_understanding.py           # PDF extraction, chunking, citations

    security/                         # Defense-in-depth security
      pii_redactor.py                 # Regex PII scrubbing
      prompt_guard.py                 # Heuristic injection detection
      ssrf_guard.py                   # DNS pinning, private IP blocking
      tool_quarantine.py              # Tool output envelope
      email_allowlist.py              # Outbound email pinning

    memory/                           # State and memory
      store.py                        # pgvector semantic store
      session_store.py                # Conversation persistence
      durable_facts.py                # Durable facts + derived status

    skills/                           # Progressive disclosure skills
      registry.py                     # Skill discovery + registration
      progressive.py                  # Advertise -> Load -> Execute
      security.py                     # Symlink/path-traversal protection
      sources/                        # File, inline, class, MCP-based

    handoff/                          # Inter-agent communication
      dispatcher.py                   # Message routing
      queues.py                       # Queue management
      cancellation.py                 # Cooperative AbortSignal propagation
      types.py                        # Handoff message types

    observability/                    # Observability stack
      tracing.py                      # OpenTelemetry auto-instrumentation
      metrics.py                      # Prometheus /metrics endpoint
      cost_tracker.py                 # tiktoken token counting + cost table
      evaluation.py                   # LLM-as-judge
      audit.py                        # Immutable audit log

    marketplace/                      # Template marketplace
      registry.py                     # manifest.yaml schema + validation
      installer.py                    # One-click install
      sandbox.py                      # Secure reviewer gateway

    cdc/                              # Change Data Capture
      poller.py                       # DB trigger -> change_log -> poller
      broadcaster.py                  # Fan-out to SSE, WebSocket, cache

    browser/                          # Per-worker browser isolation
      isolation.py                    # Isolated Chrome profiles per session
      cdp.py                          # CDP automation bridge

    web/                              # Next.js 14 frontend
      package.json                    # React 19, React Flow, Zustand, Tailwind
      tsconfig.json
      tailwind.config.js
      postcss.config.js
      next.config.js
      Dockerfile
      src/
        app/                          # App Router pages
          layout.tsx                  # AppShell (sidebar + topbar)
          globals.css                 # OKLCH design token system
          page.tsx                    # Dashboard / Overview
          agents/page.tsx             # Agent cards with filter
          workflows/page.tsx          # React Flow visual graph editor
          runs/page.tsx               # Live runs table + KPIs
          knowledge/page.tsx          # Knowledge base management
          marketplace/page.tsx        # Template marketplace
          chat/page.tsx               # Chat interface
          settings/page.tsx           # Platform settings
        components/
          ui/                         # Design system atoms (Badge, Button, Panel, Kpi)
          graph-editor/               # NodePalette + ConfigPanel
          dashboard/                  # RunsTable
          chatkit/                    # ChatPanel
          marketplace/                # MarketplaceGrid
        hooks/                        # Custom React hooks
        stores/app.ts                 # Zustand global state
        lib/api.ts                    # openapi-fetch client

  docker/
    docker-compose.yml                # Production stack (api, webapp, postgres, redis)
    docker-compose.dev.yml            # Dev overrides (volume mounts, hot reload)
    Dockerfile.api                    # Multi-stage API build

  k8s/
    base/                             # K8s manifests (namespace, api, postgres, redis, ingress)
    overlays/                         # Environment overlays
```

## Features

- **5 Orchestration Patterns**: Sequential, Concurrent, Handoff, Group Chat, Magentic
- **Agent Workflows**: Hybrid LangGraph + deterministic workflow nodes
- **Visual Graph Editor**: React Flow drag-and-drop with 13 custom node types (Supervisor, Agent, Tool, Knowledge, If/Else, Loop, HTTP, Code, Start, End, Approval)
- **8 Enterprise Connectors**: HubSpot, Salesforce, Jira, GitHub, Slack, ServiceNow, SAP, Microsoft Graph
- **5-Layer Security**: SecurityHeaders -> RBAC -> RateLimit -> Security (PII + prompt guard) -> Audit
- **Knowledge & RAG**: pgvector vector store + GraphRAG + hybrid retrieval
- **Agent Switching**: Mid-session LLM/agent replacement with durable saga
- **Marketplace**: Template registry with sandboxed validation
- **Observability**: OpenTelemetry, Prometheus, cost tracking, LLM evaluation
- **Durable Facts**: Status derived at read time, never stored (eliminates staleness)

## API

Interactive API docs at `/docs` (Swagger UI) or `/redoc` (ReDoc).

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/auth/register | Register user |
| POST | /api/v1/auth/login | Login |
| GET | /api/v1/auth/me | Current user |
| POST | /api/v1/workflows | Create workflow |
| GET | /api/v1/workflows | List workflows |
| PUT | /api/v1/workflows/{id} | Update workflow |
| DELETE | /api/v1/workflows/{id} | Delete workflow |
| POST | /api/v1/workflows/{id}/runs | Start workflow run |
| POST | /api/v1/agents | Create agent |
| GET | /api/v1/agents | List agents |
| POST | /api/v1/knowledge/{id}/query | Query knowledge base |
| GET | /api/v1/metrics/prometheus | Prometheus metrics |
| GET | /health | Health check |

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_ASYNC_URL` | Async PostgreSQL URL | postgresql+asyncpg://nexusforge:nexusforge@localhost:5432/nexusforge |
| `DB_SYNC_URL` | Sync PostgreSQL URL | postgresql://nexusforge:nexusforge@localhost:5432/nexusforge |
| `REDIS_URL` | Redis URL | redis://localhost:6379/0 |
| `AUTH_SECRET_KEY` | JWT signing key | (generated) |
| `NEXUSFORGE_ENVIRONMENT` | Environment | development |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, LangGraph, FastAPI, SQLAlchemy, Alembic |
| Frontend | Next.js 14+, React 19, TypeScript, React Flow, Tailwind CSS v3, Zustand |
| Database | PostgreSQL 16 + pgvector |
| Cache/Queues | Redis 7 (Streams, Pub/Sub) |
| Deployment | Docker Compose + Kubernetes |

## License

MIT
