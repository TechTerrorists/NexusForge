"use client";

import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, FolderGit2, GitBranch, Loader2, Plus, RefreshCw, ShieldAlert } from "lucide-react";
import { api, Repository } from "@/lib/nexus";

type Preflight = { ready: boolean; checks: Record<string, { ok: boolean; message?: string; value?: string }> };

export default function RepositoriesPage() {
  const [items, setItems] = useState<Repository[]>([]);
  const [checks, setChecks] = useState<Record<string, Preflight>>({});
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [branch, setBranch] = useState("main");
  const [commands, setCommands] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => api<Repository[]>("/api/v1/repositories").then(setItems).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load repositories"));
  useEffect(() => { void load(); }, []);

  async function inspect(repository: Repository) {
    setChecks((current) => ({ ...current, [repository.id]: { ready: false, checks: { loading: { ok: true, message: "Inspecting…" } } } }));
    try {
      const result = await api<Preflight>(`/api/v1/repositories/${repository.id}/preflight`);
      setChecks((current) => ({ ...current, [repository.id]: result }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Preflight failed");
    }
  }

  async function register(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const allowedCommands = commands.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => line.split(/\s+/));
      const repository = await api<Repository>("/api/v1/repositories", { method: "POST", body: JSON.stringify({ name, local_path: path, default_branch: branch, allowed_commands: allowedCommands }) });
      setItems((current) => [...current, repository]);
      setName(""); setPath(""); setBranch("main"); setCommands(""); setShowForm(false);
      await inspect(repository);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Registration failed"); }
    finally { setBusy(false); }
  }

  return <div className="mission-page">
    <header className="mission-heading"><div><p className="eyebrow">Execution boundaries</p><h1>Repositories</h1><p>Registered source checkouts are inspected here. Agents operate only on managed clones and isolated worktrees.</p></div><button className="btn primary" onClick={() => setShowForm((value) => !value)}><Plus size={14} /> Register repository</button></header>
    {error && <div className="error-state">{error}</div>}
    {showForm && <form className="panel panel-body mb-5 grid gap-3 lg:grid-cols-[1fr_2fr_160px_auto]" onSubmit={register}>
      <label className="detail-label">Name<input className="field" required value={name} onChange={(event) => setName(event.target.value)} placeholder="Project name" /></label>
      <label className="detail-label">Path visible to API<input className="field font-mono" required value={path} onChange={(event) => setPath(event.target.value)} placeholder="/projects/my-app" /></label>
      <label className="detail-label">Default branch<input className="field font-mono" required value={branch} onChange={(event) => setBranch(event.target.value)} /></label>
      <label className="detail-label lg:col-span-3">Acceptance commands (one argv command per line)<textarea className="field font-mono min-h-20" value={commands} onChange={(event) => setCommands(event.target.value)} placeholder={"npm test\nnpm run lint"} /></label>
      <button className="btn primary self-end" disabled={busy}>{busy ? <Loader2 className="animate-spin" size={14} /> : <FolderGit2 size={14} />} Register</button>
    </form>}
    <div className="grid gap-4 xl:grid-cols-2">
      {items.map((repository) => {
        const preflight = checks[repository.id];
        return <section className="panel" key={repository.id}>
          <div className="panel-head"><div className="flex items-center gap-3"><div className="role-mark"><FolderGit2 size={16} /></div><div><h2 className="text-sm font-semibold">{repository.name}</h2><p className="text-[11px] font-mono mt-1" style={{ color: "var(--fg-muted)" }}>{repository.local_path}</p></div></div><span className={`badge ${preflight?.ready ? "emerald" : preflight ? "red" : ""}`}>{preflight?.ready ? "ready" : preflight ? "attention" : "unchecked"}</span></div>
          <div className="panel-body space-y-4">
            <div className="detail-row"><GitBranch size={13} /> Target branch <span className="ml-auto font-mono">{repository.default_branch}</span></div>
            <div className="detail-row"><ShieldAlert size={13} /> Acceptance checks <span className="ml-auto font-mono">{repository.allowed_commands.length || "diff only"}</span></div>
            {preflight && <div className="grid gap-2 sm:grid-cols-2">{Object.entries(preflight.checks).map(([key, check]) => <div className="preflight-check" key={key}>{check.ok ? <CheckCircle2 size={13} style={{ color: "var(--emerald-4)" }} /> : <ShieldAlert size={13} style={{ color: "var(--red-4)" }} />}<span><strong>{key.replaceAll("_", " ")}</strong><small>{check.message || check.value || (check.ok ? "Passed" : "Blocked")}</small></span></div>)}</div>}
            <button className="btn sm" onClick={() => inspect(repository)}><RefreshCw size={12} /> Run preflight</button>
          </div>
        </section>;
      })}
      {!items.length && <div className="panel empty-state min-h-64 xl:col-span-2"><FolderGit2 size={22} /><span>No repositories registered. Add one to begin planning a software task.</span></div>}
    </div>
  </div>;
}
