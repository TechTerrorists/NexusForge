"use client";

import { useCallback, useState } from "react";
import { addEdge, Background, Controls, ReactFlow, type Connection, type Edge, type Node, useEdgesState, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/nexus";

type NodeType = "start" | "task" | "agent" | "condition" | "approval" | "notification" | "end";
const nodeTypes: NodeType[] = ["start", "task", "agent", "condition", "approval", "notification", "end"];

const initialNodes: Node[] = [
  { id: "start", type: "input", position: { x: 80, y: 160 }, data: { label: "Start" } },
  { id: "task", position: { x: 300, y: 160 }, data: { label: "Describe task", kind: "task" } },
  { id: "end", type: "output", position: { x: 540, y: 160 }, data: { label: "End" } },
];
const initialEdges: Edge[] = [{ id: "start-task", source: "start", target: "task" }, { id: "task-end", source: "task", target: "end" }];

function toGraph(nodes: Node[], edges: Edge[]) {
  return { nodes: nodes.map((node) => ({ id: node.id, type: (node.data.kind || (node.id === "start" ? "start" : node.id === "end" ? "end" : "task")) as NodeType, position: node.position, data: node.data })), edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })) };
}

export default function WorkflowsPage() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [name, setName] = useState("Simple automation");
  const [notice, setNotice] = useState("Only safe v1 nodes are available. Notifications require an approval node immediately before them.");
  const onConnect = useCallback((connection: Connection) => setEdges((items) => addEdge(connection, items)), [setEdges]);
  const addNode = (kind: NodeType) => {
    const id = `${kind}-${Date.now()}`;
    setNodes((items) => [...items, { id, position: { x: 250 + items.length * 35, y: 70 + items.length * 45 }, data: { label: kind.replaceAll("_", " "), kind } }]);
  };
  const validate = async () => {
    try { const response = await api<{ valid: boolean; errors?: string[] }>("/api/v1/workflow-graphs/validate", { method: "POST", body: JSON.stringify({ graph_config: toGraph(nodes, edges) }) }); setNotice(response.valid ? "Graph is valid and ready to save." : response.errors?.join(" · ") || "Graph is invalid."); } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Validation failed"); }
  };
  const save = async () => {
    try { await api("/api/v1/workflows", { method: "POST", body: JSON.stringify({ name, description: "Custom safe automation", graph_config: toGraph(nodes, edges) }) }); setNotice("Workflow saved as a draft. Validate it before activating or running it."); } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Unable to save workflow"); }
  };
  return <div className="flex flex-col h-full">
    <header className="flex items-center justify-between gap-3 px-5 py-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}><div><input value={name} onChange={(event) => setName(event.target.value)} aria-label="Workflow name" className="text-base font-semibold bg-transparent" style={{ color: "var(--fg-primary)" }} /><p className="text-xs mt-1" style={{ color: "var(--fg-muted)" }}>{notice}</p></div><div className="flex gap-2"><button className="btn" onClick={validate}>Validate</button><button className="btn primary" onClick={save}>Save draft</button></div></header>
    <div className="flex flex-1 min-h-0"><aside className="w-52 p-3" style={{ borderRight: "1px solid var(--border-subtle)" }}><p className="text-[10px] font-semibold tracking-widest uppercase mb-2" style={{ color: "var(--fg-muted)" }}>Safe nodes</p>{nodeTypes.map((kind) => <button key={kind} onClick={() => addNode(kind)} disabled={kind === "start" || kind === "end"} className="w-full text-left rounded px-2 py-2 text-xs mb-1 disabled:opacity-40" style={{ background: "var(--bg-elevated)", color: "var(--fg-secondary)" }}>+ {kind.replaceAll("_", " ")}</button>)}<p className="text-[11px] mt-4" style={{ color: "var(--fg-muted)" }}>Code, raw HTTP, loops, and unmanaged tools are intentionally unavailable in v1.</p></aside><div className="flex-1"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView><Background /><Controls /></ReactFlow></div></div>
  </div>;
}
