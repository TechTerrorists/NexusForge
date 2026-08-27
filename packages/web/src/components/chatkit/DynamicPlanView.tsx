"use client";

import { Check, Clock, GitBranch, Loader2, Shield, Zap } from "lucide-react";
import type { PlanStep } from "@/lib/nexus";
import { getPhaseColor, getPhaseLabel } from "@/lib/nexus";

const STATUS_ICONS: Record<string, typeof Clock> = {
  pending: Clock,
  running: Loader2,
  completed: Check,
  failed: Shield,
};

const STATUS_COLORS: Record<string, string> = {
  pending: "var(--fg-muted)",
  running: "var(--blue-4)",
  completed: "var(--green-4)",
  failed: "var(--red-4)",
};

type Props = {
  steps: PlanStep[];
  goal: string;
  status: string;
};

export default function DynamicPlanView({ steps, goal, status }: Props) {
  const phases = Array.from(new Set(steps.map((s) => s.nexus_phase)));
  const phaseSteps = phases.map((phase) => ({
    phase,
    steps: steps.filter((s) => s.nexus_phase === phase),
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs" style={{ color: "var(--fg-muted)" }}>
        <GitBranch size={12} />
        <span>{steps.length} steps across {phases.length} NEXUS phases</span>
      </div>

      {phaseSteps.map(({ phase, steps: phaseStepList }) => (
        <div key={phase} className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--border-subtle)" }}>
          <div
            className="px-3 py-2 flex items-center gap-2"
            style={{ background: getPhaseColor(phase) + "15", borderLeft: `3px solid ${getPhaseColor(phase)}` }}
          >
            <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: getPhaseColor(phase) }}>
              {getPhaseLabel(phase)}
            </span>
            <span className="text-xs" style={{ color: "var(--fg-muted)" }}>
              {phaseStepList.length} step{phaseStepList.length > 1 ? "s" : ""}
            </span>
          </div>

          <div className="divide-y" style={{ borderColor: "var(--border-subtle)" }}>
            {phaseStepList.map((step) => {
              const Icon = STATUS_ICONS[step.status] || Clock;
              return (
                <div key={step.id} className="px-3 py-2.5 flex gap-3 items-start">
                  <Icon
                    size={14}
                    className={`mt-0.5 shrink-0 ${step.status === "running" ? "animate-spin" : ""}`}
                    style={{ color: STATUS_COLORS[step.status] || "var(--fg-muted)" }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{step.title}</span>
                      {step.writes_code && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--amber-4)" + "20", color: "var(--amber-4)" }}>
                          code
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--bg-elevated)", color: "var(--blue-4)" }}>
                        {step.role || step.skill}
                      </span>
                      {step.depends_on.length > 0 && (
                        <span className="text-xs" style={{ color: "var(--fg-muted)" }}>
                          after {step.depends_on.join(", ")}
                        </span>
                      )}
                      {step.parallel_group && (
                        <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--green-4)" + "15", color: "var(--green-4)" }}>
                          parallel
                        </span>
                      )}
                    </div>
                    {step.acceptance_criteria && (
                      <p className="text-xs mt-1 truncate" style={{ color: "var(--fg-muted)" }}>
                        {step.acceptance_criteria}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
