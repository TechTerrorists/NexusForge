"use client";

import { useState } from "react";
import { ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";

type RunStatus = string;

interface Run {
  id: string;
  workflow: string;
  status: RunStatus;
  duration: string;
  cost: string;
  createdAt: string;
}

interface RunsTableProps {
  runs: Run[];
}

type SortKey = "id" | "workflow" | "status" | "duration" | "cost" | "createdAt";

const STATUS_BADGE: Record<string, string> = {
  completed: "badge emerald",
  running: "badge blue",
  queued: "badge amber",
  failed: "badge red",
  cancelled: "badge",
  pending: "badge amber",
  awaiting_approval: "badge amber",
  needs_review: "badge purple",
};

function parseDuration(s: string): number {
  const match = s.match(/(\d+\.?\d*)/);
  return match ? parseFloat(match[1]) : 0;
}

function parseCost(s: string): number {
  const match = s.replace(/[$,]/g, "").match(/(\d+\.?\d*)/);
  return match ? parseFloat(match[1]) : 0;
}

export default function RunsTable({ runs }: RunsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("createdAt");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = [...runs].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "id": cmp = a.id.localeCompare(b.id); break;
      case "workflow": cmp = a.workflow.localeCompare(b.workflow); break;
      case "status": cmp = a.status.localeCompare(b.status); break;
      case "duration": cmp = parseDuration(a.duration) - parseDuration(b.duration); break;
      case "cost": cmp = parseCost(a.cost) - parseCost(b.cost); break;
      case "createdAt": cmp = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(); break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ArrowUpDown size={10} />;
    return sortDir === "asc" ? <ArrowUp size={10} /> : <ArrowDown size={10} />;
  };

  const columns: { key: SortKey; label: string; className?: string }[] = [
    { key: "id", label: "Run", className: "w-24" },
    { key: "workflow", label: "Workflow" },
    { key: "status", label: "Status", className: "w-28" },
    { key: "duration", label: "Duration", className: "w-24" },
    { key: "cost", label: "Cost", className: "w-20" },
    { key: "createdAt", label: "Created", className: "w-40" },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`${col.className || ""} cursor-pointer select-none`}
                onClick={() => handleSort(col.key)}
              >
                <div className="flex items-center gap-1">
                  {col.label}
                  <SortIcon col={col.key} />
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((run) => (
            <tr key={run.id}>
              <td className="id">{run.id}</td>
              <td className="name">{run.workflow}</td>
              <td>
                <span className={STATUS_BADGE[run.status]}>
                  ● {run.status.replaceAll("_", " ")}
                </span>
              </td>
              <td className="num" style={{ color: "var(--fg-muted)" }}>{run.duration}</td>
              <td className="num" style={{ color: "var(--fg-muted)" }}>{run.cost}</td>
              <td style={{ color: "var(--fg-muted)", fontSize: "11.5px" }} suppressHydrationWarning>
                {new Date(run.createdAt).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
