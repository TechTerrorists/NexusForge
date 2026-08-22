"use client";

import { Panel, PanelHead, PanelBody, Badge, Kpi } from "@/components/ui";
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
  { id: "run-4d7b", workflow: "Email Campaign", status: "completed" as const, duration: "9.1s", cost: "$0.08", createdAt: "2025-12-15T09:30:00Z" },
  { id: "run-0e3f", workflow: "Invoice Processing", status: "failed" as const, duration: "4.5s", cost: "$0.03", createdAt: "2025-12-15T09:22:00Z" },
];

export default function RunsPage() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Live Runs</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
            10 runs in the last 24h · 2 active
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn sm">Filter</button>
          <button className="btn sm">Export</button>
        </div>
      </div>

      <div className="kpi-strip">
        <Kpi label="Total runs" value="10" delta="+3 vs yesterday" deltaDirection="up" />
        <Kpi label="Success rate" value="70" unit="%" delta="7 of 10 succeeded" deltaDirection="neutral" />
        <Kpi label="Total cost" value="$0.96" delta="$0.096/run avg" deltaDirection="neutral" />
        <Kpi label="Avg latency" value="13.0" unit="s" delta="−1.4s vs yesterday" deltaDirection="up" />
        <Kpi label="Failed" value="2" delta="needs attention" deltaDirection="down" />
      </div>

      <Panel>
        <PanelHead>
          <span className="title">All Runs</span>
          <div className="flex items-center gap-2">
            <Badge variant="blue">2 running</Badge>
            <Badge variant="amber">1 queued</Badge>
          </div>
        </PanelHead>
        <PanelBody flush>
          <RunsTable runs={DEMO_RUNS} />
        </PanelBody>
      </Panel>
    </div>
  );
}
