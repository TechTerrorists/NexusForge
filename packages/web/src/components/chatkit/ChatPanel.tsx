"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, Check, FolderGit2, Loader2, Send, User } from "lucide-react";
import { api, Repository, TaskPlan } from "@/lib/nexus";
import DynamicPlanView from "./DynamicPlanView";
import AgentCommunication from "./AgentCommunication";

type Message = { id: string; role: "user" | "assistant"; content: string };

export default function ChatPanel() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoryId, setRepositoryId] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [plan, setPlan] = useState<TaskPlan | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showRegistration, setShowRegistration] = useState(false);
  const [repoName, setRepoName] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [repoBranch, setRepoBranch] = useState("main");
  const [registering, setRegistering] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Repository[]>("/api/v1/repositories").then((items) => {
      setRepositories(items);
      if (items[0]) setRepositoryId(items[0].id);
    }).catch((reason) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, plan]);

  async function ensureSession() {
    if (sessionId) return sessionId;
    if (!repositoryId) throw new Error("Register and select a repository first.");
    const session = await api<{ id: string }>("/api/v1/chat/sessions", {
      method: "POST", body: JSON.stringify({ repository_id: repositoryId, title: "Software task" }),
    });
    setSessionId(session.id);
    return session.id;
  }

  async function registerRepository(event: FormEvent) {
    event.preventDefault();
    if (!repoName.trim() || !repoPath.trim() || registering) return;
    setRegistering(true); setError("");
    try {
      const repository = await api<Repository>("/api/v1/repositories", {
        method: "POST",
        body: JSON.stringify({
          name: repoName.trim(),
          local_path: repoPath.trim(),
          default_branch: repoBranch.trim() || "main",
          allowed_commands: [],
        }),
      });
      setRepositories((items) => [...items, repository]);
      setRepositoryId(repository.id);
      setSessionId(null); setPlan(null);
      setRepoName(""); setRepoPath(""); setRepoBranch("main");
      setShowRegistration(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to register repository");
    } finally { setRegistering(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || loading) return;
    const content = input.trim();
    setMessages((items) => [...items, { id: `local-${Date.now()}`, role: "user", content }]);
    setInput(""); setError(""); setLoading(true);
    try {
      const id = await ensureSession();
      const response = await api<{ message: string; plan: TaskPlan }>(`/api/v1/chat/sessions/${id}/messages`, {
        method: "POST", body: JSON.stringify({ content }),
      });
      setMessages((items) => [...items, { id: `assistant-${Date.now()}`, role: "assistant", content: response.message }]);
      setPlan(response.plan);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create plan");
    } finally { setLoading(false); }
  }

  async function decide(approved: boolean) {
    if (!plan) return;
    setLoading(true); setError("");
    try {
      const response = await api<{ status: string; run_id?: string }>(`/api/v1/plans/${plan.id}/decision`, {
        method: "POST", body: JSON.stringify({ approved }),
      });
      setPlan({ ...plan, status: response.status });
      if (response.run_id) setRunId(response.run_id);
      setMessages((items) => [...items, {
        id: `decision-${Date.now()}`, role: "assistant",
        content: approved ? `Team started in isolated worktrees. Track run ${response.run_id} from Live Runs.` : "Plan rejected. Send a revised task when you are ready.",
      }]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update plan"); }
    finally { setLoading(false); }
  }

  return <div className="h-full flex flex-col max-w-5xl mx-auto w-full p-6 gap-4 overflow-hidden">
    <header className="flex items-end justify-between gap-4 shrink-0">
      <div><h1 className="text-xl font-semibold">AI Team</h1><p className="text-[13px]" style={{ color: "var(--fg-muted)" }}>Describe a software task. The manager proposes roles and dependencies before anything runs.</p></div>
      <div className="flex items-end gap-2">
        <label className="text-xs" style={{ color: "var(--fg-muted)" }}>Repository
          <select aria-label="Repository" value={repositoryId} onChange={(event) => { setRepositoryId(event.target.value); setSessionId(null); setPlan(null); }} className="block mt-1 px-2 py-1.5 rounded" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }}>
            <option value="">Select repository</option>{repositories.map((repository) => <option key={repository.id} value={repository.id}>{repository.name}</option>)}
          </select>
        </label>
        <button type="button" className="btn" onClick={() => setShowRegistration((value) => !value)}><FolderGit2 size={14} /> Register</button>
      </div>
    </header>
    {repositories.length === 0 && <div className="panel p-3 text-sm shrink-0" style={{ color: "var(--amber-4)" }}>No repository is registered yet. Register a local Git checkout below before assigning a task.</div>}
    {showRegistration && <form onSubmit={registerRepository} className="panel p-4 space-y-3 shrink-0">
      <div><div className="font-medium text-sm">Register local Git checkout</div><p className="text-xs mt-1" style={{ color: "var(--fg-muted)" }}>Use an absolute path inside the configured projects mount (the same path must be visible to the API container). The folder must already be a Git repository.</p></div>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="text-xs" style={{ color: "var(--fg-muted)" }}>Name<input required value={repoName} onChange={(event) => setRepoName(event.target.value)} placeholder="My project" className="block w-full mt-1 rounded px-2 py-2 text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }} /></label>
        <label className="text-xs md:col-span-2" style={{ color: "var(--fg-muted)" }}>Absolute path<input required value={repoPath} onChange={(event) => setRepoPath(event.target.value)} placeholder="/home/you/projects/my-project" className="block w-full mt-1 rounded px-2 py-2 text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }} /></label>
      </div>
      <div className="flex gap-2 items-end"><label className="text-xs" style={{ color: "var(--fg-muted)" }}>Default branch<input value={repoBranch} onChange={(event) => setRepoBranch(event.target.value)} className="block w-36 mt-1 rounded px-2 py-2 text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }} /></label><button className="btn primary" disabled={registering}>{registering ? <Loader2 className="animate-spin" size={14} /> : <FolderGit2 size={14} />} Register repository</button></div>
    </form>}
    <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 min-h-0">
      <section className="panel p-4 min-h-[120px]">
        {messages.length === 0 && <div className="grid place-items-center text-center py-8"><div><Bot size={28} className="mx-auto" style={{ color: "var(--blue-4)" }} /><p className="text-sm mt-2" style={{ color: "var(--fg-muted)" }}>I will staff the right specialists, show their workflow, and keep code changes isolated until you review them.</p></div></div>}
        {messages.map((message) => <div key={message.id} className={`flex gap-2 ${message.role === "user" ? "justify-end" : ""}`}>
          {message.role === "assistant" && <Bot size={18} style={{ color: "var(--blue-4)"}} />}
          <div className="max-w-[75%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap" style={{ background: message.role === "user" ? "var(--blue-3)" : "var(--bg-elevated)", color: message.role === "user" ? "#0a0a0f" : "var(--fg-secondary)" }}>{message.content}</div>
          {message.role === "user" && <User size={18} style={{ color: "var(--fg-muted)" }} />}
        </div>)}
      </section>
      {plan && <section className="panel">
        <div className="panel-head">
          <span className="title">Proposed team plan</span>
          <span className="badge amber">{plan.status.replaceAll("_", " ")}</span>
        </div>
        <div className="panel-body space-y-3">
          <p className="text-sm">{plan.goal}</p>
          <DynamicPlanView steps={plan.steps} goal={plan.goal} status={plan.status} />
          {plan.status === "awaiting_approval" && <div className="flex gap-2 pt-2">
            <button className="btn primary" disabled={loading} onClick={() => decide(true)}><Check size={14} /> Approve & start</button>
            <button className="btn" disabled={loading} onClick={() => decide(false)}>Reject</button>
          </div>}
        </div>
      </section>}
      {runId && <AgentCommunication runId={runId} />}
      {error && <p className="text-sm" style={{ color: "var(--red-4)" }}>{error}</p>}
    </div>
    <form onSubmit={submit} className="flex gap-2 shrink-0"><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="e.g. Add a dark-mode regression test and fix any failures" className="flex-1 rounded p-3 text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-default)" }} /> <button className="btn primary" disabled={loading || !input.trim()}>{loading ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />} Plan task</button></form>
  </div>;
}
