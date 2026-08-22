"use client";

import { Kpi, Panel, PanelHead, PanelBody, Badge } from "@/components/ui";
import RunsTable from "@/components/dashboard/RunsTable";

const DEMO_RUNS = [
  { id: "run-8f2a", workflow: "Sales Outreach Pipeline", status: "completed" as const, duration: "12.4s", cost: "$0.18", createdAt: "2025-12-15T10:32:00Z" },
  { id: "run-3c1b", workflow: "Support Ticket Triage", status: "running" as const, duration: "3.1s", cost: "$0.04", createdAt: "2025-12-15T10:28:00Z" },
  { id: "run-7d4e", workflow: "Code Review - PR #892", status: "queued" as const, duration: "—", cost: "—", createdAt: "2025-12-15T10:25:00Z" },
  { id: "run-1a9f", workflow: "Data Pipeline ETL", status: "completed" as const, duration: "45.2s", cost: "$0.32", createdAt: "2025-12-15T10:15:00Z" },
  { id: "run-5e8c", workflow: "Document Processing", status: "failed" as const, duration: "8.7s", cost: "$0.06", createdAt: "2025-12-15T10:02:00Z" },
  { id: "run-2b6d", workflow: "Research Synthesis", status: "completed" as const, duration: "22.1s", cost: "$0.14", createdAt: "2025-12-15T09:50:00Z" },
  { id: "run-9f4a", workflow: "Customer Onboarding", status: "completed" as const, duration: "5.3s", cost: "$0.02", createdAt: "2025-12-15T09:42:00Z" },
  { id: "run-6c2e", workflow: "Security Scan", status: "running" as const, duration: "1.8s", cost: "$0.01", createdAt: "2025-12-15T09:38:00Z" },
];

export default function DashboardPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Operations overview</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
            NexusForge workspace · last 24h
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn sm" disabled>Last 24h ▾</button>
          <a href="/workflows" className="btn sm primary">+ New workflow</a>
        </div>
      </div>

      <div className="kpi-strip">
        <Kpi label="Active runs" value="2" delta="3 completed today" deltaDirection="up" />
        <Kpi label="Success rate" value="87" unit="%" delta="vs 82% yesterday" deltaDirection="up" />
        <Kpi label="Total spend" value="$0.77" delta="$0.10/run avg" deltaDirection="neutral" />
        <Kpi label="Avg latency" value="12.4" unit="s" delta="−2.1s vs yesterday" deltaDirection="up" />
        <Kpi label="Agents" value="6" delta="3 active" deltaDirection="neutral" />
      </div>

      <div className="grid gap-4" style={{ gridTemplateColumns: "1.5fr 1fr" }}>
        <Panel>
          <PanelHead>
            <span className="title">Recent Runs</span>
            <span style={{ color: "var(--fg-muted)", fontFamily: "var(--font-mono)", fontSize: "11px" }}>
              /api/metrics/runs
            </span>
          </PanelHead>
          <PanelBody flush>
            <RunsTable runs={DEMO_RUNS} />
          </PanelBody>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHead>
              <span className="title">System Health</span>
            </PanelHead>
            <PanelBody>
              <div className="space-y-2.5">
                {[
                  { name: "API Server", ms: "12ms" },
                  { name: "PostgreSQL", ms: "2ms" },
                  { name: "Redis", ms: "1ms" },
                  { name: "LangGraph", ms: "8ms" },
                ].map((svc) => (
                  <div key={svc.name} className="flex items-center justify-between py-1">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--emerald-4)" }} />
                      <span className="text-[13px]" style={{ color: "var(--fg-secondary)" }}>{svc.name}</span>
                    </div>
                    <span style={{ color: "var(--fg-muted)", fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                      {svc.ms}
                    </span>
                  </div>
                ))}
              </div>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHead>
              <span className="title">Top Agents</span>
            </PanelHead>
            <PanelBody>
              <div className="space-y-2.5">
                {[
                  { name: "Research Agent", runs: 142, color: "blue" as const },
                  { name: "Data Analyzer", runs: 231, color: "purple" as const },
                  { name: "Code Review", runs: 87, color: "emerald" as const },
                  { name: "Support Triage", runs: 56, color: "amber" as const },
                ].map((agent) => (
                  <div key={agent.name} className="flex items-center justify-between py-1">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold"
                        style={{
                          background: agent.color === "blue" ? "var(--blue-1)" : agent.color === "purple" ? "var(--purple-1)" : agent.color === "emerald" ? "var(--emerald-1)" : "var(--amber-1)",
                          color: agent.color === "blue" ? "var(--blue-4)" : agent.color === "purple" ? "var(--purple-4)" : agent.color === "emerald" ? "var(--emerald-4)" : "var(--amber-4)",
                          border: `1px solid ${agent.color === "blue" ? "var(--blue-2)" : agent.color === "purple" ? "var(--purple-2)" : agent.color === "emerald" ? "var(--emerald-2)" : "var(--amber-2)"}`,
                        }}
                      >
                        {agent.name[0]}
                      </div>
                      <span className="text-[13px]" style={{ color: "var(--fg-secondary)" }}>{agent.name}</span>
                    </div>
                    <Badge variant={agent.color}>{agent.runs} runs</Badge>
                  </div>
                ))}
              </div>
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}
