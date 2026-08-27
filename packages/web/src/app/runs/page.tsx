"use client";

import { useEffect, useMemo, useState } from "react";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import {
  CheckCircle2,
  FileCode2,
  FileText,
  GitBranch,
  Loader2,
  Square,
  XCircle,
} from "lucide-react";
import "@xyflow/react/dist/style.css";
import { api, formatDuration, TaskPlan, TaskRun } from "@/lib/nexus";
import RunsTable from "@/components/dashboard/RunsTable";

type Review = {
  decision: "approved" | "rejected";
  feedback: string;
  reviewed_at: string;
};

type RunOutput = {
  branch?: string;
  summary?: string;
  review?: Review;
};

type Detail = {
  id: string;
  status: string;
  error?: string | null;
  output?: RunOutput | null;
  plan: TaskPlan | null;
  events: {
    sequence: number;
    type: string;
    actor: string;
    payload?: Record<string, unknown>;
    created_at: string;
  }[];
};

type Artifact = {
  id: string;
  kind: string;
  name: string;
  content: string;
  metadata: Record<string, unknown>;
};

type ReviewResponse = {
  status: string;
  output: RunOutput;
};

const statusColor: Record<string, string> = {
  completed: "#22c55e",
  running: "#60a5fa",
  failed: "#f87171",
  needs_review: "#c084fc",
  pending: "#fbbf24",
};

function artifactLabel(kind: string): string {
  if (kind === "agent_output") return "Agent output";
  if (kind === "diff_summary") return "Diff summary";
  if (kind === "git_diff") return "Git diff";
  if (kind === "branch") return "Branch";
  return kind.replaceAll("_", " ");
}

export default function RunsPage() {
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [stopping, setStopping] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    let inflight = false;
    const load = async () => {
      if (inflight) return;
      inflight = true;
      try {
        const items = await api<TaskRun[]>("/api/v1/runs");
        setRuns(items);
        setError("");
        setSelected((current) => current || items[0]?.id || null);
      } catch {
        // Retry on the next polling interval.
      } finally {
        inflight = false;
      }
    };
    void load();
    const id = window.setInterval(load, 4000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setArtifacts([]);
      return;
    }
    let active = true;
    setFeedback("");
    const load = () => {
      Promise.all([
        api<Detail>(`/api/v1/runs/${selected}/detail`),
        api<Artifact[]>(`/api/v1/runs/${selected}/artifacts`),
      ])
        .then(([nextDetail, nextArtifacts]) => {
          if (!active) return;
          setDetail(nextDetail);
          setArtifacts(nextArtifacts);
          setActiveArtifactId((current) => {
            if (nextArtifacts.some((artifact) => artifact.id === current)) return current;
            const preferred = [...nextArtifacts]
              .reverse()
              .find((artifact) => artifact.kind === "agent_output");
            return preferred?.id || nextArtifacts[0]?.id || null;
          });
        })
        .catch((reason) => {
          if (active) {
            setError(reason instanceof Error ? reason.message : "Unable to load run output");
          }
        });
    };
    load();
    const id = window.setInterval(load, 4000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [selected]);

  const graph = useMemo(() => {
    const steps = detail?.plan?.steps || [];
    const nodes: Node[] = steps.map((step, index) => ({
      id: step.key,
      position: { x: 80 + index * 230, y: 110 },
      data: { label: `${step.title}\n${step.skill}\n${step.status}` },
      style: {
        width: 180,
        whiteSpace: "pre-line",
        border: `2px solid ${statusColor[step.status] || "#64748b"}`,
        borderRadius: 10,
        background: "#151521",
        color: "#e5e7eb",
        padding: 12,
        fontSize: 12,
      },
    }));
    const edges: Edge[] = steps.flatMap((step) =>
      step.depends_on.map((dependency) => ({
        id: `${dependency}-${step.key}`,
        source: dependency,
        target: step.key,
        animated: step.status === "running",
        style: { stroke: "#64748b" },
      })),
    );
    return { nodes, edges };
  }, [detail]);

  const activeArtifact = artifacts.find((artifact) => artifact.id === activeArtifactId);
  const diffArtifacts = artifacts.filter((artifact) =>
    ["diff_summary", "git_diff"].includes(artifact.kind),
  );
  const hasTrackedChanges = diffArtifacts.some((artifact) => artifact.content.trim());
  const canStop = detail?.status === "running" || detail?.status === "pending";
  const canReview = detail?.status === "needs_review";

  async function stopRun() {
    if (!selected || !canStop || stopping) return;
    setStopping(true);
    setError("");
    try {
      await api(`/api/v1/runs/${selected}/cancel`, { method: "POST" });
      setDetail((current) => (current ? { ...current, status: "cancelling" } : current));
      setRuns((items) =>
        items.map((run) =>
          run.id === selected ? { ...run, status: "cancelling" } : run,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to stop run");
    } finally {
      setStopping(false);
    }
  }

  async function submitReview(approved: boolean) {
    if (!selected || !canReview || reviewing) return;
    if (!approved && !feedback.trim()) {
      setError("Add feedback explaining why the result is being rejected.");
      return;
    }
    setReviewing(true);
    setError("");
    try {
      const result = await api<ReviewResponse>(`/api/v1/runs/${selected}/review`, {
        method: "POST",
        body: JSON.stringify({ approved, feedback: feedback.trim() }),
      });
      setDetail((current) =>
        current ? { ...current, status: result.status, output: result.output } : current,
      );
      setRuns((items) =>
        items.map((run) =>
          run.id === selected
            ? { ...run, status: result.status, output: result.output }
            : run,
        ),
      );
      setFeedback("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to submit review");
    } finally {
      setReviewing(false);
    }
  }

  const tableRuns = runs.map((run) => ({
    id: run.id.slice(0, 8),
    workflow: run.workflow,
    status: run.status,
    duration: formatDuration(run),
    cost: `$${run.cost_usd.toFixed(3)}`,
    createdAt: run.created_at,
  }));

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Live Runs</h1>
        <p className="text-[13px]" style={{ color: "var(--fg-muted)" }}>
          Inspect worker output, repository changes, and review decisions.
        </p>
      </div>

      {error && <p className="text-sm" style={{ color: "var(--red-4)" }}>{error}</p>}

      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <div className="panel overflow-hidden">
          <div className="panel-head"><span className="title">Runs</span></div>
          <div className="max-h-[440px] overflow-auto"><RunsTable runs={tableRuns} /></div>
          <div className="p-3 space-y-1">
            {runs.map((run) => (
              <button
                key={run.id}
                onClick={() => setSelected(run.id)}
                className="w-full text-left rounded px-2 py-1.5 text-xs"
                style={{
                  background: selected === run.id ? "var(--blue-1)" : "transparent",
                  color: "var(--fg-secondary)",
                }}
              >
                {run.id.slice(0, 8)} · {run.status.replaceAll("_", " ")}
              </button>
            ))}
          </div>
        </div>

        <div className="panel min-h-[440px]">
          <div className="panel-head">
            <span className="title">Team workflow</span>
            <div className="flex items-center gap-2">
              <span className="badge blue">{detail?.status || "select a run"}</span>
              {canStop && (
                <button className="btn text-xs" onClick={stopRun} disabled={stopping}>
                  {stopping
                    ? <Loader2 className="animate-spin" size={13} />
                    : <Square size={13} fill="currentColor" />}
                  Stop run
                </button>
              )}
            </div>
          </div>
          <div className="h-[380px]">
            {detail?.plan ? (
              <ReactFlow
                nodes={graph.nodes}
                edges={graph.edges}
                fitView
                nodesDraggable={false}
                nodesConnectable={false}
              >
                <Background />
                <Controls />
              </ReactFlow>
            ) : (
              <div className="h-full grid place-items-center text-sm" style={{ color: "var(--fg-muted)" }}>
                Select a run to inspect its workflow.
              </div>
            )}
          </div>
        </div>
      </div>

      {detail && (
        <div className="panel">
          <div className="panel-head">
            <div>
              <span className="title">Review output</span>
              {detail.output?.branch && (
                <span className="ml-3 text-[11px] font-mono" style={{ color: "var(--fg-muted)" }}>
                  <GitBranch className="inline mr-1" size={12} />
                  {detail.output.branch}
                </span>
              )}
            </div>
            {detail.output?.review && (
              <span className={detail.output.review.decision === "approved" ? "badge emerald" : "badge red"}>
                {detail.output.review.decision}
              </span>
            )}
          </div>

          <div className="panel-body space-y-4">
            <p className="text-sm" style={{ color: "var(--fg-secondary)" }}>
              {detail.output?.summary || "Review the stored worker artifacts for this run."}
            </p>

            {!hasTrackedChanges && detail.status === "needs_review" && (
              <div
                className="rounded-md border px-3 py-2 text-xs"
                style={{ borderColor: "rgba(212,148,58,.45)", background: "rgba(58,40,16,.35)", color: "var(--amber-4)" }}
              >
                No tracked file changes were captured. Review the agent outputs before accepting;
                this run may contain advisory text only.
              </div>
            )}

            <div className="grid min-h-[360px] overflow-hidden rounded-lg border lg:grid-cols-[240px_1fr]" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="border-r p-2 overflow-auto" style={{ borderColor: "var(--border-subtle)", background: "var(--bg-inset)" }}>
                {artifacts.length ? artifacts.map((artifact) => (
                  <button
                    key={artifact.id}
                    onClick={() => setActiveArtifactId(artifact.id)}
                    className="mb-1 flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left"
                    style={{
                      background: activeArtifactId === artifact.id ? "var(--blue-1)" : "transparent",
                      color: activeArtifactId === artifact.id ? "var(--blue-5)" : "var(--fg-secondary)",
                    }}
                  >
                    {artifact.kind.includes("diff")
                      ? <FileCode2 className="mt-0.5 shrink-0" size={14} />
                      : <FileText className="mt-0.5 shrink-0" size={14} />}
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium">{artifact.name}</span>
                      <span className="block text-[10px]" style={{ color: "var(--fg-muted)" }}>
                        {artifactLabel(artifact.kind)}
                      </span>
                    </span>
                  </button>
                )) : (
                  <p className="p-3 text-xs" style={{ color: "var(--fg-muted)" }}>No artifacts stored.</p>
                )}
              </div>

              <div className="min-w-0">
                <div className="flex h-10 items-center justify-between border-b px-3" style={{ borderColor: "var(--border-subtle)" }}>
                  <span className="truncate text-xs font-medium">{activeArtifact?.name || "Select an artifact"}</span>
                  {typeof activeArtifact?.metadata.skill === "string" && (
                    <span className="badge blue">{activeArtifact.metadata.skill}</span>
                  )}
                </div>
                <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words p-4 text-[12px] leading-5" style={{ color: "var(--fg-secondary)", fontFamily: "var(--font-mono)" }}>
                  {activeArtifact
                    ? activeArtifact.content || "This artifact is empty. No tracked changes were produced."
                    : "Select an artifact to inspect its full output."}
                </pre>
              </div>
            </div>

            {canReview && (
              <div className="rounded-lg border p-4" style={{ borderColor: "var(--border-default)", background: "var(--bg-elevated)" }}>
                <label className="mb-2 block text-xs font-medium" style={{ color: "var(--fg-secondary)" }}>
                  Review feedback <span style={{ color: "var(--fg-muted)" }}>(required when rejecting)</span>
                </label>
                <textarea
                  value={feedback}
                  onChange={(event) => setFeedback(event.target.value)}
                  rows={3}
                  maxLength={4000}
                  placeholder="Record what was verified or what needs to change…"
                  className="w-full resize-y rounded-md border px-3 py-2 text-sm outline-none"
                  style={{ background: "var(--bg-inset)", borderColor: "var(--border-default)", color: "var(--fg-primary)" }}
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                  <span className="text-[11px]" style={{ color: "var(--fg-muted)" }}>
                    Accepting marks the run complete. The isolated branch is not merged automatically.
                  </span>
                  <div className="flex gap-2">
                    <button className="btn text-xs" disabled={reviewing} onClick={() => submitReview(false)} style={{ color: "var(--red-4)" }}>
                      {reviewing ? <Loader2 className="animate-spin" size={13} /> : <XCircle size={14} />}
                      Reject result
                    </button>
                    <button className="btn primary text-xs" disabled={reviewing} onClick={() => submitReview(true)}>
                      {reviewing ? <Loader2 className="animate-spin" size={13} /> : <CheckCircle2 size={14} />}
                      Accept result
                    </button>
                  </div>
                </div>
              </div>
            )}

            {detail.output?.review?.feedback && (
              <div className="text-xs" style={{ color: "var(--fg-secondary)" }}>
                <span className="font-medium">Review feedback:</span> {detail.output.review.feedback}
              </div>
            )}
          </div>
        </div>
      )}

      {detail && (
        <div className="panel">
          <div className="panel-head"><span className="title">Event stream</span></div>
          <div className="panel-body space-y-2">
            {detail.events.length ? detail.events.map((event) => (
              <div key={event.sequence} className="text-xs">
                <span style={{ color: "var(--blue-4)" }}>#{event.sequence} {event.actor}</span>
                {" · "}{event.type.replaceAll("_", " ")}
              </div>
            )) : (
              <span className="text-xs" style={{ color: "var(--fg-muted)" }}>Waiting for the first event.</span>
            )}
            {detail.error && <div className="text-xs" style={{ color: "var(--red-4)" }}>{detail.error}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
