const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Repository = { id: string; name: string; local_path: string; default_branch: string; allowed_commands: string[] };
export type PlanStep = {
  id: string;
  key: string;
  title: string;
  skill: string;
  depends_on: string[];
  writes_code: boolean;
  status: string;
  nexus_phase: string;
  role: string;
  parallel_group: string | null;
  acceptance_criteria: string;
};
export type TaskPlan = { id: string; goal: string; status: string; estimated_cost_usd: number; steps: PlanStep[] };
export type TaskRun = { id: string; workflow: string; status: string; tokens_used: number; cost_usd: number; started_at: string | null; completed_at: string | null; created_at: string; error?: string | null; output?: Record<string, unknown> | null };
export type AgentMessage = {
  id: string;
  sender: string;
  recipient: string;
  type: string;
  payload: Record<string, unknown>;
  artifact_refs: string[];
  timestamp: number;
  reply_to: string | null;
};

function token(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem("nf_token");
}

function apiErrorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const error = item as { loc?: unknown[]; msg?: unknown };
      if (typeof error.msg !== "string") return [];
      const location = Array.isArray(error.loc)
        ? error.loc.filter((part) => part !== "body").join(".")
        : "";
      return [location ? `${location}: ${error.msg}` : error.msg];
    });
    if (messages.length) return messages.join("; ");
  }
  return `Request failed (${status})`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const accessToken = token();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({}));
    const detail = payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail?: unknown }).detail
      : undefined;
    throw new Error(apiErrorMessage(detail, response.status));
  }
  return response.json() as Promise<T>;
}

export function formatDuration(run: TaskRun): string {
  if (!run.started_at) return "—";
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  return `${Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000))}s`;
}

const NEXUS_PHASE_COLORS: Record<string, string> = {
  discover: "#8b5cf6",
  strategize: "#3b82f6",
  scaffold: "#06b6d4",
  build: "#22c55e",
  harden: "#f59e0b",
  launch: "#ef4444",
  operate: "#6b7280",
};

export function getPhaseColor(phase: string): string {
  return NEXUS_PHASE_COLORS[phase] || "#6b7280";
}

const NEXUS_PHASE_LABELS: Record<string, string> = {
  discover: "Discover",
  strategize: "Strategize",
  scaffold: "Scaffold",
  build: "Build",
  harden: "Harden",
  launch: "Launch",
  operate: "Operate",
};

export function getPhaseLabel(phase: string): string {
  return NEXUS_PHASE_LABELS[phase] || phase;
}
