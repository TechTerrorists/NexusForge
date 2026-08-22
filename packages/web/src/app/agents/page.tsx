"use client";

import { useState } from "react";
import {
  Plus,
  Bot,
  Play,
  Square,
  Wrench,
  MoreVertical,
  Cpu,
  Activity,
} from "lucide-react";
import { Badge } from "@/components/ui";

interface Agent {
  id: string;
  name: string;
  model: string;
  status: "running" | "idle";
  tools: string[];
  runCount: number;
  description: string;
  color: "blue" | "purple" | "emerald" | "amber" | "red";
}

const DEMO_AGENTS: Agent[] = [
  {
    id: "a1", name: "Research Agent", model: "gpt-4o", status: "running",
    tools: ["web_search", "arxiv", "summarize"], runCount: 142,
    description: "Searches and summarizes academic papers and web sources.", color: "blue",
  },
  {
    id: "a2", name: "Code Review Agent", model: "claude-sonnet-4-20250514", status: "idle",
    tools: ["github", "code_analysis", "lint"], runCount: 87,
    description: "Reviews pull requests and suggests improvements.", color: "emerald",
  },
  {
    id: "a3", name: "Data Analyzer", model: "gpt-4o-mini", status: "running",
    tools: ["sql_query", "chart_gen", "pandas"], runCount: 231,
    description: "Analyzes datasets and generates visualizations.", color: "purple",
  },
  {
    id: "a4", name: "Support Triage", model: "claude-sonnet-4-20250514", status: "idle",
    tools: ["zendesk", "knowledge_base", "email"], runCount: 56,
    description: "Classifies and routes incoming support tickets.", color: "amber",
  },
  {
    id: "a5", name: "Outreach Writer", model: "gpt-4o", status: "idle",
    tools: ["crm", "email_send", "template"], runCount: 34,
    description: "Drafts personalized outreach emails from CRM data.", color: "red",
  },
  {
    id: "a6", name: "Security Scanner", model: "gpt-4o-mini", status: "running",
    tools: ["sast", "dependency_check", "secret_scan"], runCount: 19,
    description: "Scans codebases for vulnerabilities and secrets.", color: "blue",
  },
];

const COLOR_MAP = {
  blue:    { bg: "var(--blue-1)",    fg: "var(--blue-4)",    border: "var(--blue-2)" },
  purple:  { bg: "var(--purple-1)",  fg: "var(--purple-4)",  border: "var(--purple-2)" },
  emerald: { bg: "var(--emerald-1)", fg: "var(--emerald-4)", border: "var(--emerald-2)" },
  amber:   { bg: "var(--amber-1)",   fg: "var(--amber-4)",   border: "var(--amber-2)" },
  red:     { bg: "var(--red-1)",     fg: "var(--red-4)",     border: "var(--red-2)" },
};

export default function AgentsPage() {
  const [filter, setFilter] = useState<"all" | "running" | "idle">("all");

  const filtered = DEMO_AGENTS.filter(
    (a) => filter === "all" || a.status === filter
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Agents</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
            {DEMO_AGENTS.filter((a) => a.status === "running").length} running ·{" "}
            {DEMO_AGENTS.length} total
          </p>
        </div>
        <div className="flex gap-2">
          <div
            className="flex rounded-lg overflow-hidden text-[13px]"
            style={{ border: "1px solid var(--border-default)" }}
          >
            {(["all", "running", "idle"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className="px-3 py-1.5 capitalize transition-colors"
                style={{
                  background: filter === f ? "var(--blue-3)" : "var(--bg-elevated)",
                  color: filter === f ? "#0a0a0f" : "var(--fg-secondary)",
                }}
              >
                {f}
              </button>
            ))}
          </div>
          <button className="btn primary">
            <Plus size={14} />
            New Agent
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((agent) => {
          const c = COLOR_MAP[agent.color];
          return (
            <div
              key={agent.id}
              className="rounded-lg transition-shadow hover:shadow-md"
              style={{
                background: "var(--bg-canvas)",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-[11px] font-bold"
                      style={{
                        background: c.bg,
                        color: c.fg,
                        border: `1px solid ${c.border}`,
                      }}
                    >
                      {agent.name.split(" ").map(w => w[0]).join("").slice(0, 2)}
                    </div>
                    <div>
                      <h3 className="text-[13px] font-semibold" style={{ color: "var(--fg-primary)" }}>
                        {agent.name}
                      </h3>
                      <p className="text-[11px]" style={{ color: "var(--fg-muted)" }}>
                        {agent.model}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={agent.status === "running" ? "emerald" : "default"}>
                      {agent.status === "running" && (
                        <Activity size={10} className="animate-pulse" />
                      )}
                      {agent.status}
                    </Badge>
                  </div>
                </div>

                <p className="text-[13px] mb-3" style={{ color: "var(--fg-muted)" }}>
                  {agent.description}
                </p>

                <div className="flex flex-wrap gap-1 mb-3">
                  {agent.tools.map((tool) => (
                    <span
                      key={tool}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px]"
                      style={{
                        background: "var(--bg-elevated)",
                        color: "var(--fg-muted)",
                        border: "1px solid var(--border-subtle)",
                      }}
                    >
                      <Wrench size={9} />
                      {tool}
                    </span>
                  ))}
                </div>

                <div
                  className="flex items-center justify-between pt-3"
                  style={{ borderTop: "1px solid var(--border-subtle)" }}
                >
                  <div className="flex items-center gap-1 text-[11px]" style={{ color: "var(--fg-muted)" }}>
                    <Cpu size={12} />
                    {agent.runCount} runs
                  </div>
                  <div className="flex gap-1">
                    {agent.status === "running" ? (
                      <button
                        className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium"
                        style={{ background: "var(--red-1)", color: "var(--red-4)" }}
                      >
                        <Square size={10} />
                        Stop
                      </button>
                    ) : (
                      <button
                        className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium"
                        style={{ background: "var(--emerald-1)", color: "var(--emerald-4)" }}
                      >
                        <Play size={10} />
                        Run
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
