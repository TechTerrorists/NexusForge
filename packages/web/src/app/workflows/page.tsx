"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { addEdge, Background, Controls, Position, ReactFlow, type Connection, type Edge, type Node, useEdgesState, useNodesState } from "@xyflow/react";
import { Beaker, Bot, Braces, CheckCircle2, Clock3, GitBranch, Globe2, Hand, Play, Plus, Save, Send, TerminalSquare, Webhook, Workflow as WorkflowIcon } from "lucide-react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/nexus";

type NodeKind = "start" | "http_request" | "map" | "condition" | "foreach" | "approval" | "command" | "notification" | "llm" | "agent" | "end";
type WorkflowRecord = { id: string; name: string; description: string; status: string; version: number; graph_config: Record<string, unknown> };
type Version = { id: string; version: number; status: string; validation_errors: string[] };
type Trigger = { id: string; type: string; config: Record<string, unknown>; active: boolean; next_fire_at: string | null };
const palette: { kind: NodeKind; label: string; icon: typeof Play; token: string }[] = [
  { kind: "http_request", label: "HTTP request", icon: Globe2, token: "0" }, { kind: "map", label: "Map data", icon: Braces, token: "0" },
  { kind: "condition", label: "Condition", icon: GitBranch, token: "0" }, { kind: "foreach", label: "Bounded foreach", icon: WorkflowIcon, token: "0" },
  { kind: "approval", label: "Approval", icon: Hand, token: "0" }, { kind: "command", label: "Safe command", icon: TerminalSquare, token: "0" },
  { kind: "notification", label: "Notification", icon: Send, token: "0" }, { kind: "llm", label: "LLM call", icon: Bot, token: "LLM" },
  { kind: "agent", label: "Agent task", icon: Bot, token: "LLM" },
];
const initialNodes: Node[] = [
  { id: "start", type: "input", sourcePosition: Position.Right, position: { x: 60, y: 180 }, data: { label: "Manual trigger", kind: "start" } },
  { id: "map-1", sourcePosition: Position.Right, targetPosition: Position.Left, position: { x: 310, y: 180 }, data: { label: "Map input", kind: "map", mapping: { value: "{{ input.value }}" } } },
  { id: "end", type: "output", targetPosition: Position.Left, position: { x: 570, y: 180 }, data: { label: "Complete", kind: "end" } },
];
const initialEdges: Edge[] = [{ id: "start-map", source: "start", target: "map-1" }, { id: "map-end", source: "map-1", target: "end" }];

function graphPayload(nodes: Node[], edges: Edge[]) {
  return { nodes: nodes.map((node) => ({ id: node.id, type: node.data.kind, position: node.position, data: node.data })), edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, data: edge.data })) };
}

export default function AutomationsPage() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [records, setRecords] = useState<WorkflowRecord[]>([]);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [name, setName] = useState("Release readiness check");
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [notice, setNotice] = useState("Draft changes are local until you save an immutable version.");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const activeVersion = versions.find((version) => version.status === "active");
  const currentNode = nodes.find((node) => node.id === selectedNode);
  const deterministic = useMemo(() => !nodes.some((node) => ["llm", "agent"].includes(String(node.data.kind))), [nodes]);

  const reload = useCallback(async () => {
    try { setRecords(await api<WorkflowRecord[]>("/api/v1/workflows")); } catch { /* explicit empty state below */ }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    if (!workflowId) { setVersions([]); setTriggers([]); return; }
    Promise.all([api<Version[]>(`/api/v1/workflows/${workflowId}/versions`), api<Trigger[]>(`/api/v1/workflows/${workflowId}/triggers`)]).then(([nextVersions, nextTriggers]) => { setVersions(nextVersions); setTriggers(nextTriggers); });
  }, [workflowId]);
  const onConnect = useCallback((connection: Connection) => setEdges((items) => {
    const source = nodes.find((node) => node.id === connection.source);
    if (source?.data.kind !== "condition") return addEdge(connection, items);
    const branchIndex = items.filter((edge) => edge.source === connection.source).length;
    return addEdge({ ...connection, label: branchIndex === 0 ? "true" : "false", data: { when: branchIndex === 0 } }, items);
  }), [nodes, setEdges]);

  function selectRecord(record: WorkflowRecord) {
    setWorkflowId(record.id); setName(record.name); setErrors([]);
    const graph = record.graph_config as { nodes?: Array<{ id: string; type: NodeKind; position?: { x: number; y: number }; data?: Record<string, unknown> }>; edges?: Edge[] };
    if (Array.isArray(graph.nodes) && Array.isArray(graph.edges)) {
      setNodes(graph.nodes.map((node, index) => ({ id: node.id, type: node.type === "start" ? "input" : node.type === "end" ? "output" : undefined, sourcePosition: node.type === "end" ? undefined : Position.Right, targetPosition: node.type === "start" ? undefined : Position.Left, position: node.position || { x: 80 + index * 220, y: 180 }, data: { ...(node.data || {}), kind: node.type } })));
      setEdges(graph.edges);
    }
  }

  function addNode(kind: NodeKind) {
    const definition = palette.find((item) => item.kind === kind)!;
    const id = `${kind}-${Date.now()}`;
    const defaults: Record<string, unknown> = kind === "foreach" ? { max_items: 25, items: "input.items" } : kind === "http_request" ? { method: "GET", url: "https://api.example.com/status", allowed_domains: ["api.example.com"] } : kind === "notification" ? { url: "https://hooks.example.com/nexusforge", allowed_domains: ["hooks.example.com"], message: "Workflow completed: {{ input.value }}" } : kind === "command" ? { argv: ["git", "status", "--short"] } : kind === "condition" ? { left: "input.value", operator: "exists", right: null } : kind === "map" ? { mapping: { value: "{{ input.value }}" } } : kind === "agent" ? { prompt: "Summarize {{ input.value }}", role: "", budget_usd: 1, tool_grants: [] } : kind === "llm" ? { prompt: "Summarize {{ input.value }}" } : {};
    setNodes((items) => [...items, { id, sourcePosition: Position.Right, targetPosition: Position.Left, position: { x: 230 + items.length * 45, y: 80 + (items.length % 4) * 100 }, data: { label: definition.label, kind, ...defaults } }]);
    setSelectedNode(id);
  }

  async function validate() {
    try {
      const response = await api<{ valid: boolean; errors?: string[] }>("/api/v1/workflow-graphs/validate", { method: "POST", body: JSON.stringify({ graph_config: graphPayload(nodes, edges) }) });
      setErrors(response.errors || []); setNotice(response.valid ? "Validation passed. Save this graph as an immutable version." : "Resolve the attached validation errors before activation.");
      return response.valid;
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Validation failed"); return false; }
  }

  async function save() {
    if (!(await validate())) return;
    setBusy(true);
    try {
      if (!workflowId) {
        const created = await api<WorkflowRecord>("/api/v1/workflows", { method: "POST", body: JSON.stringify({ name, description: "Typed deterministic automation", graph_config: graphPayload(nodes, edges) }) });
        setWorkflowId(created.id); setNotice("Version 1 saved and validated. Activate it when ready."); await reload();
      } else {
        await api(`/api/v1/workflows/${workflowId}/versions`, { method: "POST", body: JSON.stringify({ graph_config: graphPayload(nodes, edges), input_schema: {} }) });
        const next = await api<Version[]>(`/api/v1/workflows/${workflowId}/versions`); setVersions(next); setNotice("A new immutable version was saved.");
      }
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Unable to save workflow"); }
    finally { setBusy(false); }
  }

  async function activate() {
    if (!workflowId || !versions[0]) return;
    setBusy(true);
    try { await api(`/api/v1/workflows/${workflowId}/versions/${versions[0].id}/activate`, { method: "POST" }); setVersions((items) => items.map((item, index) => ({ ...item, status: index === 0 ? "active" : item.status === "active" ? "validated" : item.status }))); setNotice(`Version ${versions[0].version} is active.`); await reload(); }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : "Activation failed"); }
    finally { setBusy(false); }
  }

  async function testRun() {
    if (!workflowId) return;
    setBusy(true);
    try { const run = await api<{ id: string }>(`/api/v1/workflows/${workflowId}/runs`, { method: "POST", body: JSON.stringify({ workflow_version_id: activeVersion?.id || versions[0]?.id, payload: { value: "sample input", items: [1, 2, 3] }, test_mode: true }) }); window.location.href = `/runs?run=${run.id}`; }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : "Test run failed"); setBusy(false); }
  }

  async function addTrigger(type: "cron" | "webhook") {
    if (!workflowId || !activeVersion) { setNotice("Activate a version before adding triggers."); return; }
    try {
      const result = await api<{ id: string; type: string; config: Record<string, unknown>; active: boolean; webhook_secret?: string }>(`/api/v1/workflows/${workflowId}/triggers`, {
        method: "POST",
        body: JSON.stringify({ workflow_version_id: activeVersion.id, trigger_type: type, config: type === "cron" ? { cron: "0 9 * * 1-5", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, misfire_policy: "skip" } : { payload_schema: {} } }),
      });
      setTriggers((items) => [...items, { ...result, next_fire_at: null }]);
      setNotice(result.webhook_secret ? `Webhook created. Copy this secret now: ${result.webhook_secret}` : "Weekday 09:00 cron trigger created in your local timezone.");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Unable to create trigger"); }
  }

  function updateNodeData(field: string, value: unknown) { setNodes((items) => items.map((node) => node.id === selectedNode ? { ...node, data: { ...node.data, [field]: value } } : node)); }

  return <div className="automation-shell">
    <aside className="automation-library"><div className="p-4 border-b" style={{ borderColor: "var(--border-subtle)" }}><p className="eyebrow">Versioned flows</p><h1 className="text-lg font-semibold mt-1">Automations</h1></div><div className="p-2">{records.map((record) => <button key={record.id} onClick={() => selectRecord(record)} className={`automation-record ${workflowId === record.id ? "active" : ""}`}><span className="status-dot" style={{ background: record.status === "active" ? "var(--emerald-4)" : "var(--fg-muted)" }} /><span><strong>{record.name}</strong><small>v{record.version} · {record.status}</small></span></button>)}<button className="automation-record" onClick={() => { setWorkflowId(null); setNodes(initialNodes); setEdges(initialEdges); setName("Untitled automation"); }}><Plus size={13} /><span><strong>New automation</strong><small>Start a draft</small></span></button></div></aside>
    <main className="automation-main"><header className="automation-bar"><div><input aria-label="Automation name" value={name} onChange={(event) => setName(event.target.value)} /><p>{notice}</p></div><div className="flex gap-2"><span className={`badge ${deterministic ? "emerald" : "purple"}`}>{deterministic ? "0 LLM tokens" : "metered AI nodes"}</span><button className="btn" disabled={busy} onClick={testRun}><Beaker size={13} /> Test run</button><button className="btn" disabled={busy} onClick={save}><Save size={13} /> Save version</button><button className="btn primary" disabled={busy || !workflowId || !versions.length} onClick={activate}><Play size={13} /> Activate latest</button></div></header>
      <div className="automation-workspace"><aside className="node-palette"><p className="detail-label">Typed nodes</p>{palette.map(({ kind, label, icon: Icon, token }) => <button key={kind} onClick={() => addNode(kind)}><Icon size={14} /><span>{label}</span><small>{token}</small></button>)}<div className="mt-5"><p className="detail-label">Triggers</p><div className="trigger-summary"><Play size={12} /> Manual</div>{triggers.map((trigger) => <div className="trigger-summary" key={trigger.id}>{trigger.type === "cron" ? <Clock3 size={12} /> : <Webhook size={12} />}{trigger.type}<span>{trigger.active ? "active" : "paused"}</span></div>)}</div></aside>
        <section className="automation-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelectedNode(node.id)} fitView><Background gap={22} size={1} /><Controls /></ReactFlow>{errors.length > 0 && <div className="validation-stack">{errors.map((error) => <div key={error}><CheckCircle2 size={12} />{error}</div>)}</div>}</section>
        <aside className="node-config"><div className="panel-head"><span className="title">Node configuration</span></div>{currentNode ? <div className="panel-body space-y-4"><p className="eyebrow">{String(currentNode.data.kind).replaceAll("_", " ")}</p><label className="detail-label">Label<input className="field" value={String(currentNode.data.label || "")} onChange={(event) => updateNodeData("label", event.target.value)} /></label>{Object.entries(currentNode.data).filter(([key]) => !["kind", "label"].includes(key)).map(([key, value]) => <label className="detail-label" key={key}>{key.replaceAll("_", " ")}<textarea className="field font-mono min-h-20" value={typeof value === "string" ? value : JSON.stringify(value, null, 2)} onChange={(event) => { try { updateNodeData(key, JSON.parse(event.target.value)); } catch { updateNodeData(key, event.target.value); } }} /></label>)}</div> : <div className="empty-state min-h-48">Select a node to configure its typed inputs.</div>}<div className="panel-body border-t" style={{ borderColor: "var(--border-subtle)" }}><p className="detail-label mb-3">Trigger management</p><div className="flex gap-2"><button className="btn sm" onClick={() => addTrigger("cron")}><Clock3 size={11} /> Add cron</button><button className="btn sm" onClick={() => addTrigger("webhook")}><Webhook size={11} /> Add webhook</button></div><p className="mt-3 text-[10px]" style={{ color: "var(--fg-muted)" }}>Webhook secrets are shown once. Cron defaults to weekdays at 09:00 in this browser&apos;s timezone.</p></div></aside>
      </div>
    </main>
  </div>;
}
