"use client";

import { useEffect, useMemo, useState } from "react";
import { Background, Controls, Position, ReactFlow, type Edge, type Node } from "@xyflow/react";
import {
  Activity,
  CheckCircle2,
  FileCode2,
  FileText,
  GitMerge,
  Loader2,
  MessageSquareText,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  Square,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import "@xyflow/react/dist/style.css";
import { api, formatDuration, streamEvents, TaskPlan, TaskRun } from "@/lib/nexus";

type Check = { command: string[]; exit_code: number; status: string; output: string };
type Review = { decision: "approved" | "rejected"; feedback: string; reviewed_at: string };
type RunOutput = { branch?: string; base_revision?: string; integration_path?: string; summary?: string; changed_files?: string[]; checks?: Check[]; review?: Review; merge?: { status: string; revision: string } };
type AgentInstance = { id: string; task_step_id: string | null; name: string; role_slug: string; status: string; model: Record<string, string>; tool_grants: string[] };
type Event = { sequence: number; type: string; actor: string; payload?: Record<string, unknown>; agent_instance_id?: string | null; task_step_id?: string | null; created_at: string };
type Detail = { id: string; trace_id: string; run_kind: string; status: string; error?: string | null; output?: RunOutput | null; plan: TaskPlan | null; agents: AgentInstance[]; events: Event[] };
type Artifact = { id: string; kind: string; name: string; content: string; metadata: Record<string, unknown> };
type InspectorTab = "activity" | "artifacts" | "checks";

const statusColor: Record<string, string> = {
  completed: "#4ade80", running: "#6ea1f0", failed: "#f06a6a", awaiting_review: "#b794f6",
  needs_review: "#b794f6", changes_requested: "#f0b44a", queued: "#f0b44a", pending: "#7b7b91", blocked: "#f06a6a",
};
const terminalStatuses = new Set(["completed", "failed", "cancelled", "timeout", "awaiting_review", "needs_review"]);

export default function RunsPage() {
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const [tab, setTab] = useState<InspectorTab>("activity");
  const [feedback, setFeedback] = useState("");
  const [targetBranch, setTargetBranch] = useState("main");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("run");
    const load = async () => {
      try {
        const items = await api<TaskRun[]>("/api/v1/runs");
        setRuns(items);
        setSelected((current) => current || (requested && items.some((item) => item.id === requested) ? requested : items[0]?.id || null));
      } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load runs"); }
    };
    void load();
    const timer = window.setInterval(load, 8000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selected) { setDetail(null); setArtifacts([]); return; }
    let active = true;
    let reconnectTimer = 0;
    let refreshTimer = 0;
    let artifactRefreshTimer = 0;
    let controller: AbortController | null = null;
    let lastSequence = 0;
    let latestStatus = "";
    let reconnectDelay = 1500;
    let loadInFlight: Promise<Detail | null> | null = null;
    let pendingArtifactRefresh = false;
    const load = async (includeArtifacts = false): Promise<Detail | null> => {
      if (loadInFlight) {
        pendingArtifactRefresh ||= includeArtifacts;
        return loadInFlight;
      }
      loadInFlight = (async () => {
      try {
        const nextDetail = await api<Detail>(`/api/v1/runs/${selected}/detail`);
        const nextArtifacts = includeArtifacts
          ? await api<Artifact[]>(`/api/v1/runs/${selected}/artifacts`)
          : null;
        if (!active) return null;
        latestStatus = nextDetail.status;
        setDetail(nextDetail); setError("");
        lastSequence = Math.max(lastSequence, ...nextDetail.events.map((event) => event.sequence), 0);
        if (nextArtifacts) {
          setArtifacts(nextArtifacts);
          setActiveArtifactId((current) => current && nextArtifacts.some((item) => item.id === current) ? current : [...nextArtifacts].reverse().find((item) => item.kind === "git_diff")?.id || nextArtifacts.at(-1)?.id || null);
        }
        return nextDetail;
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load run detail");
        return null;
      }
      })();
      try { return await loadInFlight; }
      finally {
        loadInFlight = null;
        if (active && pendingArtifactRefresh) {
          pendingArtifactRefresh = false;
          window.clearTimeout(artifactRefreshTimer);
          artifactRefreshTimer = window.setTimeout(() => { void load(true); }, 100);
        }
      }
    };
    const connect = async () => {
      if (!active || terminalStatuses.has(latestStatus)) return;
      controller = new AbortController();
      let receivedEvent = false;
      try {
        await streamEvents(`/api/v1/runs/${selected}/events`, lastSequence, (event) => {
          receivedEvent = true;
          lastSequence = Math.max(lastSequence, event.id);
          window.clearTimeout(refreshTimer);
          refreshTimer = window.setTimeout(() => { void load(false); }, 750);
          if (/artifact|step_completed|run_ready|merge/.test(event.type)) {
            window.clearTimeout(artifactRefreshTimer);
            artifactRefreshTimer = window.setTimeout(() => { void load(true); }, 1200);
          }
        }, controller.signal);
      } catch (reason) {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof Error ? `${reason.message}; reconnecting…` : "Event stream interrupted; reconnecting…");
        }
      }
      const current = active ? await load(true) : null;
      if (!active || (current && terminalStatuses.has(current.status))) return;
      reconnectDelay = receivedEvent ? 1500 : Math.min(reconnectDelay * 2, 30000);
      reconnectTimer = window.setTimeout(() => { void connect(); }, reconnectDelay);
    };
    const start = async () => {
      const initial = await load(true);
      if (active && initial && !terminalStatuses.has(initial.status)) void connect();
    };
    setFeedback(""); void start();
    return () => {
      active = false;
      controller?.abort();
      window.clearTimeout(reconnectTimer);
      window.clearTimeout(refreshTimer);
      window.clearTimeout(artifactRefreshTimer);
    };
  }, [selected]);

  const graph = useMemo(() => {
    const steps = detail?.plan?.steps || [];
    const depth = new Map<string, number>();
    const calculateDepth = (key: string): number => {
      if (depth.has(key)) return depth.get(key)!;
      const step = steps.find((item) => item.key === key);
      const value = step?.depends_on.length ? Math.max(...step.depends_on.map(calculateDepth)) + 1 : 0;
      depth.set(key, value); return value;
    };
    const columns = new Map<number, number>();
    const nodes: Node[] = steps.map((step) => {
      const column = calculateDepth(step.key); const row = columns.get(column) || 0; columns.set(column, row + 1);
      const agent = detail?.agents.find((item) => item.task_step_id === step.id);
      return {
        id: step.key,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        position: { x: 60 + column * 260, y: 70 + row * 160 },
        data: { label: <div className="topology-node"><div className="flex items-center justify-between gap-2"><span className="phase-dot" style={{ background: statusColor[step.status] || "#606070" }} /><small>{step.nexus_phase}</small></div><strong>{step.title}</strong><span>{agent?.role_slug || step.role_slug || step.skill}</span><em>{step.status.replaceAll("_", " ")}</em></div> },
        style: { width: 210, border: `1px solid ${statusColor[step.status] || "#404050"}`, borderRadius: 12, background: "rgba(18,18,28,.96)", color: "#f0f0f5", padding: 0, boxShadow: step.status === "running" ? `0 0 24px ${statusColor.running}33` : "none" },
      };
    });
    const edges: Edge[] = steps.flatMap((step) => step.depends_on.map((dependency) => ({ id: `${dependency}-${step.key}`, source: dependency, target: step.key, animated: step.status === "running", style: { stroke: step.status === "running" ? statusColor.running : "#343442" } })));
    return { nodes, edges };
  }, [detail]);

  const activeArtifact = artifacts.find((artifact) => artifact.id === activeArtifactId);
  const output = detail?.output || {};
  const canStop = detail && ["planning", "queued", "pending", "running", "blocked", "awaiting_input"].includes(detail.status);
  const canResume = detail?.run_kind === "agentic_task" && ["failed", "timeout"].includes(detail.status);
  const canReview = detail && ["awaiting_review", "needs_review"].includes(detail.status);
  const canMerge = detail?.status === "completed" && output.review?.decision === "approved" && output.merge?.status !== "merged";

  async function action(path: string, body?: object) {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try {
      await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      const next = await api<Detail>(`/api/v1/runs/${selected}/detail`); setDetail(next);
      const items = await api<TaskRun[]>("/api/v1/runs"); setRuns(items);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Action failed"); }
    finally { setBusy(false); }
  }

  return <div className="runs-shell">
    <aside className="run-rail">
      <div className="run-rail-head"><p className="eyebrow">Execution ledger</p><h1>Runs</h1><span>{runs.length} recent</span></div>
      <div className="run-list">{runs.map((run) => <button key={run.id} onClick={() => setSelected(run.id)} className={`run-list-item ${selected === run.id ? "active" : ""}`}>
        <div className="flex items-center justify-between gap-2"><span className="run-id">{run.id.slice(0, 8)}</span><span className="status-dot" style={{ background: statusColor[run.status] || "#606070" }} /></div>
        <strong>{run.workflow.replace("AI Team: ", "")}</strong>
        <div><span>{run.status.replaceAll("_", " ")}</span><span>{formatDuration(run)}</span></div>
      </button>)}{!runs.length && <div className="empty-state min-h-48">No runs yet. Approve a task or start an automation.</div>}</div>
    </aside>

    <main className="run-main">
      <header className="run-commandbar">
        <div><div className="flex items-center gap-2"><span className={`badge ${detail?.status === "running" ? "blue" : canReview ? "purple" : detail?.status === "failed" ? "red" : ""}`}>{detail?.status?.replaceAll("_", " ") || "Select a run"}</span>{detail?.run_kind && <span className="badge">{detail.run_kind.replaceAll("_", " ")}</span>}</div><h2>{detail?.plan?.goal || runs.find((run) => run.id === selected)?.workflow || "Run mission control"}</h2><p className="font-mono">trace {detail?.trace_id?.slice(0, 16) || "—"} · {detail?.agents.length || 0} staffed agents · ${runs.find((run) => run.id === selected)?.cost_usd.toFixed(3) || "0.000"}</p></div>
        <div className="flex gap-2">
          {canResume && <button className="btn primary" disabled={busy} onClick={() => action(`/api/v1/runs/${selected}/resume`)}>{busy ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />} Resume run</button>}
          {canStop && <button className="btn" disabled={busy} onClick={() => action(`/api/v1/runs/${selected}/cancel`)}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Square size={12} />} Stop</button>}
        </div>
      </header>
      {error && <div className="error-state m-4">{error}</div>}

      <section className="topology-stage">
        {detail?.plan ? <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.25} maxZoom={1.8} nodesDraggable={false} nodesConnectable={false}><Background gap={22} size={1} /><Controls /></ReactFlow> : <div className="empty-state h-full"><Activity size={22} />Select a run to inspect its live topology.</div>}
      </section>

      <section className="run-inspector">
        <nav className="inspector-tabs">{(["activity", "artifacts", "checks"] as InspectorTab[]).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item === "activity" ? <Activity size={13} /> : item === "artifacts" ? <FileCode2 size={13} /> : <ShieldCheck size={13} />}{item}<span>{item === "activity" ? detail?.events.length || 0 : item === "artifacts" ? artifacts.length : output.checks?.length || 0}</span></button>)}</nav>
        <div className="inspector-body">
          {tab === "activity" && <div className="event-stream">{[...(detail?.events || [])].reverse().map((event) => <article key={event.sequence} className="event-row"><div className="event-icon">{event.type === "command" ? <TerminalSquare size={13} /> : event.type === "agent_message" ? <MessageSquareText size={13} /> : event.type.includes("file") ? <FileCode2 size={13} /> : <ScrollText size={13} />}</div><div><div className="flex flex-wrap items-center gap-2"><strong>{event.type.replaceAll("_", " ")}</strong><span>{event.actor}</span><time>{new Date(event.created_at).toLocaleTimeString()}</time></div><pre>{JSON.stringify(event.payload || {}, null, 2)}</pre></div></article>)}{!detail?.events.length && <div className="empty-state min-h-48">Events will appear here as the durable worker reports progress.</div>}</div>}
          {tab === "artifacts" && <div className="artifact-workspace"><aside>{artifacts.map((artifact) => <button className={activeArtifactId === artifact.id ? "active" : ""} key={artifact.id} onClick={() => setActiveArtifactId(artifact.id)}>{artifact.kind.includes("diff") ? <FileCode2 size={13} /> : <FileText size={13} />}<span><strong>{artifact.name}</strong><small>{artifact.kind.replaceAll("_", " ")}</small></span></button>)}</aside><div><header>{activeArtifact?.name || "Select an artifact"}</header><pre>{activeArtifact?.content || "No artifact selected."}</pre></div></div>}
          {tab === "checks" && <div className="checks-list">{output.checks?.map((check, index) => <article key={`${check.command.join("-")}-${index}`}><div>{check.status === "passed" ? <CheckCircle2 size={15} style={{ color: "var(--emerald-4)" }} /> : <XCircle size={15} style={{ color: "var(--red-4)" }} />}<strong>{check.command.join(" ")}</strong><span className={`badge ${check.status === "passed" ? "emerald" : "red"}`}>{check.status}</span></div>{check.output && <pre>{check.output}</pre>}</article>)}{!output.checks?.length && <div className="empty-state min-h-48">Acceptance checks appear after all steps integrate.</div>}</div>}
        </div>
      </section>

      {(canReview || canMerge || output.merge?.status === "merged") && <section className="review-dock">
        <div><p className="eyebrow">Human control point</p><h3>{canReview ? "Review the integrated result" : output.merge?.status === "merged" ? "Merged successfully" : "Approved and ready to merge"}</h3><p>{output.summary || "Final approval never merges automatically."}</p>{output.changed_files?.length ? <span className="signal-chip"><FileCode2 size={12} /> {output.changed_files.length} changed files</span> : null}</div>
        {canReview && <div className="review-actions"><textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Verification notes, or required corrections…" /><div><button className="btn" disabled={busy} onClick={() => { if (!feedback.trim()) { setError("Describe the corrections required."); return; } void action(`/api/v1/runs/${selected}/review`, { approved: false, feedback }); }}><XCircle size={13} /> Request changes</button><button className="btn primary" disabled={busy} onClick={() => action(`/api/v1/runs/${selected}/review`, { approved: true, feedback })}><CheckCircle2 size={13} /> Approve result</button></div></div>}
        {canMerge && <div className="review-actions"><label className="detail-label">Target branch<input className="field font-mono" value={targetBranch} onChange={(event) => setTargetBranch(event.target.value)} /></label><button className="btn primary" disabled={busy || !output.base_revision} onClick={() => action(`/api/v1/runs/${selected}/merge`, { target_branch: targetBranch, expected_base_revision: output.base_revision })}><GitMerge size={14} /> Merge approved result</button></div>}
        {output.merge?.status === "merged" && <span className="badge emerald"><GitMerge size={12} /> {output.merge.revision?.slice(0, 10)}</span>}
      </section>}
    </main>
  </div>;
}
