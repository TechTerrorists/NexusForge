const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Repository = { id: string; name: string; local_path: string; managed_path?: string | null; default_branch: string; allowed_commands: string[][] };
export type PlanStep = {
  id: string;
  key: string;
  title: string;
  instructions: string;
  skill: string;
  depends_on: string[];
  writes_code: boolean;
  status: string;
  nexus_phase: string;
  role: string;
  parallel_group: string | null;
  acceptance_criteria: string;
  role_slug?: string;
  expected_artifacts?: string[];
  tool_grants?: string[];
  side_effect_class?: string;
  delegation_depth?: number;
  max_retries?: number;
};
export type TaskPlan = { id: string; goal: string; status: string; estimated_cost_usd: number; constraints?: Record<string, unknown>; limits?: Record<string, number>; steps: PlanStep[] };
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
  if (detail && typeof detail === "object") {
    const structured = detail as { message?: unknown; checks?: unknown };
    const message = typeof structured.message === "string" ? structured.message : `Request failed (${status})`;
    if (structured.checks && typeof structured.checks === "object") {
      const failed = Object.entries(structured.checks as Record<string, unknown>).flatMap(([key, value]) => {
        if (!value || typeof value !== "object") return [];
        const check = value as { ok?: unknown; message?: unknown };
        if (check.ok !== false) return [];
        return [`${key.replaceAll("_", " ")}: ${typeof check.message === "string" ? check.message : "failed"}`];
      });
      return failed.length ? `${message} — ${failed.join("; ")}` : message;
    }
    return message;
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

export type ServerEvent = {
  id: number;
  type: string;
  data: { sequence?: number; actor?: string; payload?: Record<string, unknown> };
};

/** Consume an authenticated, resumable SSE response without exposing credentials in a URL. */
export async function streamEvents(
  path: string,
  after: number,
  onEvent: (event: ServerEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const headers = new Headers({ Accept: "text/event-stream" });
  const accessToken = token();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(`${API_URL}${path}${separator}after=${after}`, { headers, signal });
  if (!response.ok || !response.body) {
    throw new Error(`Event stream unavailable (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      let id = after;
      let type = "message";
      const data: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("id:")) id = Number(line.slice(3).trim()) || id;
        else if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) onEvent({ id, type, data: JSON.parse(data.join("\n")) });
    }
    if (done) return;
  }
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
