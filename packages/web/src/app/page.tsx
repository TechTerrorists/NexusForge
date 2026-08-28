"use client";

import { useEffect, useState } from "react";
import { Kpi, Panel, PanelBody, PanelHead } from "@/components/ui";
import RunsTable from "@/components/dashboard/RunsTable";
import { api, formatDuration, TaskRun } from "@/lib/nexus";

type Overview = { total_runs: number; active_runs: number; completed_runs: number; success_rate: number; total_cost_usd: number };

export default function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const load = async () => { try { const [summary, recent] = await Promise.all([api<Overview>("/api/v1/overview"), api<TaskRun[]>("/api/v1/runs?limit=8")]); setOverview(summary); setRuns(recent); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load overview"); } };
    load(); const id = window.setInterval(load, 5000); return () => window.clearInterval(id);
  }, []);
  const rows = runs.map((run) => ({ id: run.id.slice(0, 8), workflow: run.workflow, status: run.status, duration: formatDuration(run), cost: `$${run.cost_usd.toFixed(3)}`, createdAt: run.created_at }));
  return <div className="p-6 space-y-6">
    <div><p className="eyebrow">Mission control</p><h1 className="text-2xl font-semibold mt-1 tracking-tight">Command Center</h1><p className="text-[13px] mt-1" style={{ color: "var(--fg-muted)" }}>Durable status for approved software teams and deterministic automations.</p></div>
    {error && <p className="text-sm" style={{ color: "var(--red-4)" }}>{error}</p>}
    <div className="kpi-strip"><Kpi label="Total runs" value={overview?.total_runs ?? "—"} /><Kpi label="Active work" value={overview?.active_runs ?? "—"} /><Kpi label="Review / done" value={overview?.completed_runs ?? "—"} /><Kpi label="Completion" value={overview?.success_rate ?? "—"} unit={overview ? "%" : undefined} /><Kpi label="Recorded spend" value={overview ? `$${overview.total_cost_usd.toFixed(2)}` : "—"} /></div>
    <Panel><PanelHead><span className="title">Recent runs</span><a className="text-xs" style={{ color: "var(--blue-4)" }} href="/runs">Open live workflow →</a></PanelHead><PanelBody flush><RunsTable runs={rows} /></PanelBody></Panel>
  </div>;
}
