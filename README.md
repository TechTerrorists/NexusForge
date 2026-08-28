# NexusForge

NexusForge is a production-shaped hackathon project for running trustworthy AI software teams and low-cost deterministic automations.

The current product can plan a repository task, staff ephemeral agents from versioned role templates, execute approved work in managed Git clones and isolated worktrees, persist a typed activity ledger, collect changes and checks for review, and merge only after a separate explicit command. It also supports versioned deterministic workflows with manual, timezone-aware cron, and signed-webhook triggers.

Knowledge, Marketplace, remote execution, and enterprise connectors are Preview or internal packages; they are not advertised as operational product features.

## Execution model

```text
Browser mission control
        │ REST + resumable SSE
        ▼
FastAPI control plane ───────► PostgreSQL (authoritative ledger)
        │                              ▲
        │ queues durable jobs          │ leases, events, artifacts
        ▼                              │
Dedicated worker ◄──────────── Redis wake-ups/messages (optional)
        │
        ├── deterministic typed nodes (zero LLM tokens unless explicit)
        │
        └── managed clone → per-agent worktrees → integration branch
                                │
                                ▼
                      non-root Docker agent sandbox
```

PostgreSQL owns plans, runs, immutable workflow versions, jobs, agent instances, messages, delegations, node runs, events, artifacts, usage, and approvals. Redis is never the source of truth. API restarts do not terminate active work; the worker reclaims expired leases.

## Implemented surfaces

- **Tasks** — repository selection, LLM-assisted or deterministic fallback planning, relevant role retrieval, editable team/steps/criteria/limits, mandatory approval.
- **Runs** — live topology, agent instances, typed command/tool/file/check events, messages, artifacts, diffs, request-changes, approval, and guarded fast-forward merge.
- **Workforce** — versioned role catalog imported from `agency-agents`, executable capability disclosure, provenance, and live per-run instances.
- **Automations** — immutable versions, graph validation, typed nodes, test mode, approval pauses, manual runs, cron triggers, HMAC webhooks, and per-node history.
- **Repositories** — ownership-scoped registration and preflight. Agent work occurs in NexusForge-managed clones; the registered checkout is touched only by explicit merge.
- **Settings** — hot-swappable provider label, OpenAI-compatible or Anthropic protocol, endpoint, model, and encrypted API key.

## Safety boundaries

- Code-writing steps require a local or Docker tool-capable runner. HTTP-only LLM mode cannot report code work as complete.
- Docker agents run non-root, resource-limited, capability-dropped, read-only except for one worktree, and never receive the Docker socket.
- Successful code steps must produce repository changes; objective checks run before review.
- Commands and deterministic loops are allowlisted and bounded. HTTP nodes require an explicit domain allowlist and reject private, loopback, link-local, reserved, and multicast targets.
- Runner events are normalized, bounded, and secret-redacted before persistence.
- Review and merge are separate commands. Merge revalidates the target branch, cleanliness, and expected base revision; it never forces conflicts.

## Quick start

Requirements: Docker with Compose and enough permission to use the Docker socket.

```bash
cp .env.example .env
docker build -t nexusforge-opencode-runner:latest -f docker/Dockerfile.runner .
docker compose --env-file .env -f docker/docker-compose.dev.yml up --build -d
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Development API docs: `http://localhost:8000/docs`

The development stack includes `api`, `worker`, `webapp`, PostgreSQL with pgvector, and Redis. The API and worker mount `packages/` for development; the agent sandbox image is built from `docker/Dockerfile.runner`.

Run migrations in non-disposable environments instead of relying on development schema creation:

```bash
docker compose -f docker/docker-compose.dev.yml exec api \
  alembic -c packages/api/alembic.ini upgrade head
```

## Important configuration

| Variable | Purpose |
|---|---|
| `DB_ASYNC_URL` | PostgreSQL async connection |
| `REDIS_URL` | Optional delivery/wake-up channel |
| `AUTH_SECRET_KEY` | JWT signing and local secret encryption |
| `NEXUSFORGE_RUNNER_MODE` | `docker` for code; `local`/`http` are advisory-only |
| `NEXUSFORGE_RUNNER_IMAGE` | Non-root coding sandbox image |
| `NEXUSFORGE_HOST_PROJECTS_ROOT` | Host path mounted at the identical container path |
| `NEXUSFORGE_HOST_RUNS_ROOT` | Managed clone/worktree root |
| `NEXUSFORGE_AGENCY_AGENTS_PATH` | Versioned role profile source |
| `NEXUSFORGE_WORKFLOW_COMMANDS` | Comma-separated executable allowlist for command nodes |

Provider endpoint, model, protocol, and API key can be changed at runtime under Settings. New plans and subsequent worker steps read the saved tenant configuration without restarting containers.

## API contracts

Core endpoints are versioned below `/api/v1`:

- `/chat/sessions`, `/plans`, `/repositories`
- `/runs/{id}/detail`, `/events`, `/messages`, `/artifacts`, `/delegations`, `/review`, `/merge`
- `/workforce/roles`, `/workforce/skills`, `/workforce/agents`
- `/workflows/{id}/versions`, `/triggers`, `/runs`
- `/workflows/hooks/{trigger_id}`
- `/settings/llm`

Every persisted run event carries a run/trace identity, sequence, actor, optional agent/task identity, visibility, timestamp, type, and typed payload. Compatibility task/run endpoints remain while the frontend migration finishes.

## Verification

```bash
# Backend (inside the API image so PostgreSQL dependencies are identical)
docker compose -f docker/docker-compose.dev.yml exec -T api pytest packages/api/tests -q

# Frontend
cd packages/web
./node_modules/.bin/tsc --noEmit
npm run build
```

The focused test suite covers planner JSON recovery, audit/security middleware, message transport, role import, workflow validation/cron behavior, and review semantics. Full Docker runner, restart recovery, browser, and merge-drift scenarios should remain required CI gates as the project moves beyond hackathon deployment.
