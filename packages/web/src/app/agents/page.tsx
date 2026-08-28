"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, CheckCircle2, Clock3, Search, ShieldCheck, Wrench } from "lucide-react";
import { api } from "@/lib/nexus";

type Role = {
  id: string;
  slug: string;
  name: string;
  description: string;
  division: string;
  version: number;
  capabilities: string[];
  compatible_tools: string[];
  source_path: string;
  is_executable: boolean;
};

type AgentInstance = {
  id: string;
  run_id: string;
  name: string;
  role_slug: string;
  status: string;
  model: Record<string, string>;
  tool_grants: string[];
  started_at: string | null;
};

export default function WorkforcePage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [agents, setAgents] = useState<AgentInstance[]>([]);
  const [search, setSearch] = useState("");
  const [division, setDivision] = useState("all");
  const [selected, setSelected] = useState<Role | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api<{ items: Role[] }>("/api/v1/workforce/roles?limit=300"),
      api<AgentInstance[]>("/api/v1/workforce/agents?limit=50"),
    ]).then(([catalog, instances]) => {
      setRoles(catalog.items);
      setAgents(instances);
      setLoading(false);
    }).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Unable to load the workforce");
      setLoading(false);
    });
  }, []);

  const divisions = useMemo(() => ["all", ...Array.from(new Set(roles.map((role) => role.division))).sort()], [roles]);
  const filtered = useMemo(() => roles.filter((role) => {
    const matchDivision = division === "all" || role.division === division;
    const haystack = `${role.name} ${role.slug} ${role.description} ${role.capabilities.join(" ")}`.toLowerCase();
    return matchDivision && haystack.includes(search.toLowerCase());
  }), [roles, division, search]);
  const running = agents.filter((agent) => agent.status === "running");

  return <div className="mission-page">
    <header className="mission-heading">
      <div>
        <p className="eyebrow">Versioned talent registry</p>
        <h1>Workforce</h1>
        <p>Role templates become immutable, temporary agent instances only when a plan is approved.</p>
      </div>
      <div className="flex gap-2">
        <span className="signal-chip"><Activity size={13} /> {running.length} active</span>
        <span className="signal-chip"><ShieldCheck size={13} /> {roles.filter((role) => role.is_executable).length} executable</span>
      </div>
    </header>

    {error && <div className="error-state">{error}</div>}

    <section className="panel mb-5">
      <div className="panel-head"><span className="title">Active agent instances</span><span className="text-xs" style={{ color: "var(--fg-muted)" }}>Ephemeral · run scoped</span></div>
      <div className="grid gap-px sm:grid-cols-2 xl:grid-cols-4" style={{ background: "var(--border-subtle)" }}>
        {agents.slice(0, 8).map((agent) => <a href={`/runs?run=${agent.run_id}`} key={agent.id} className="p-4 block" style={{ background: "var(--bg-canvas)" }}>
          <div className="flex items-start justify-between gap-2"><Bot size={17} style={{ color: "var(--blue-4)" }} /><span className={`badge ${agent.status === "running" ? "blue" : agent.status === "completed" ? "emerald" : ""}`}>{agent.status}</span></div>
          <p className="mt-3 text-sm font-medium line-clamp-1">{agent.name}</p>
          <p className="mt-1 text-[11px] font-mono" style={{ color: "var(--fg-muted)" }}>{agent.model.model || "configured model"}</p>
        </a>)}
        {!agents.length && !loading && <div className="empty-state sm:col-span-2 xl:col-span-4"><Clock3 size={18} /><span>No agents are staffed right now. Approve a task plan to create a team.</span></div>}
      </div>
    </section>

    <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
      <section className="panel">
        <div className="panel-head gap-3">
          <span className="title">Role catalog <span className="badge">{filtered.length}</span></span>
          <div className="flex min-w-0 gap-2">
            <label className="search-field"><Search size={13} /><input aria-label="Search roles" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search roles or skills" /></label>
            <select aria-label="Division" value={division} onChange={(event) => setDivision(event.target.value)} className="field compact"><option value="all">All divisions</option>{divisions.slice(1).map((item) => <option key={item} value={item}>{item}</option>)}</select>
          </div>
        </div>
        <div className="grid gap-px md:grid-cols-2" style={{ background: "var(--border-subtle)" }}>
          {filtered.map((role) => <button key={role.id} onClick={() => setSelected(role)} className="role-card text-left">
            <div className="flex items-start justify-between gap-3">
              <div className="role-mark">{role.name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2)}</div>
              <span className={`badge ${role.is_executable ? "emerald" : "amber"}`}>{role.is_executable ? "v1 ready" : "catalog only"}</span>
            </div>
            <h2>{role.name}</h2>
            <p>{role.description || "Imported role profile"}</p>
            <div className="flex flex-wrap gap-1.5 mt-3">{role.capabilities.slice(0, 3).map((item) => <span className="capability" key={item}>{item}</span>)}</div>
            <div className="role-meta"><span>{role.division}</span><span>v{role.version}</span></div>
          </button>)}
          {!filtered.length && !loading && <div className="empty-state md:col-span-2">No role templates match this filter.</div>}
        </div>
      </section>

      <aside className="panel h-fit xl:sticky xl:top-5">
        <div className="panel-head"><span className="title">Role detail</span></div>
        {selected ? <div className="panel-body space-y-5">
          <div><p className="eyebrow">{selected.division} · version {selected.version}</p><h2 className="text-lg font-semibold mt-1">{selected.name}</h2><p className="text-sm mt-2" style={{ color: "var(--fg-secondary)" }}>{selected.description}</p></div>
          <div><p className="detail-label">Capabilities</p><div className="flex flex-wrap gap-2">{selected.capabilities.map((item) => <span className="capability" key={item}><CheckCircle2 size={10} /> {item}</span>)}</div></div>
          <div><p className="detail-label">Compatible tools</p>{selected.compatible_tools.length ? selected.compatible_tools.map((item) => <div className="detail-row" key={item}><Wrench size={12} /> {item}</div>) : <p className="text-xs" style={{ color: "var(--fg-muted)" }}>No executable tools are declared yet.</p>}</div>
          <div><p className="detail-label">Provenance</p><p className="break-all text-[11px] font-mono" style={{ color: "var(--fg-muted)" }}>{selected.source_path}</p></div>
        </div> : <div className="empty-state min-h-64">Select a role to inspect its version, tools, and provenance.</div>}
      </aside>
    </div>
  </div>;
}
