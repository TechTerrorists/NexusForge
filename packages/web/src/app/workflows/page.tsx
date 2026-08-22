"use client";

import { useCallback, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Controls,
  MiniMap,
  Background,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  addEdge,
  BackgroundVariant,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  type DefaultEdgeOptions,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import NodePalette from "@/components/graph-editor/NodePalette";
import ConfigPanel from "@/components/graph-editor/ConfigPanel";

const initialNodes: Node[] = [
  { id: "supervisor", type: "supervisor", position: { x: 400, y: 50 }, data: { label: "Supervisor" } },
  { id: "researcher", type: "agent", position: { x: 100, y: 200 }, data: { label: "Researcher", model: "gpt-4o-mini", tools: ["web_search", "arxiv"] } },
  { id: "analyzer", type: "agent", position: { x: 400, y: 200 }, data: { label: "Analyzer", model: "gpt-4o-mini", tools: ["sql_query", "chart_gen"] } },
  { id: "executor", type: "agent", position: { x: 700, y: 200 }, data: { label: "Executor", model: "gpt-4o", tools: ["github", "code_analysis"] } },
  { id: "approval", type: "approval", position: { x: 400, y: 350 }, data: { label: "Human Approval" } },
];

const initialEdges: Edge[] = [
  { id: "s-r", source: "supervisor", target: "researcher", sourceHandle: "left", animated: true, style: { stroke: "#4f8adf", strokeWidth: 2 } },
  { id: "s-a", source: "supervisor", target: "analyzer", sourceHandle: "center", animated: true, style: { stroke: "#4f8adf", strokeWidth: 2 } },
  { id: "s-e", source: "supervisor", target: "executor", sourceHandle: "right", animated: true, style: { stroke: "#4f8adf", strokeWidth: 2 } },
  { id: "r-s", source: "researcher", target: "supervisor", style: { stroke: "#404050", strokeWidth: 2 } },
  { id: "a-s", source: "analyzer", target: "supervisor", style: { stroke: "#404050", strokeWidth: 2 } },
  { id: "e-a", source: "executor", target: "approval", style: { stroke: "#d4943a", strokeWidth: 2 } },
];

const handleStyle = { width: 8, height: 8, background: "var(--fg-muted)", border: "2px solid var(--bg-canvas)" };

const nodeTypes = {
  default: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid var(--border-default)", color: "var(--fg-primary)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--fg-muted)" }}>Node</div>
      <div className="font-medium">{data.label || "Untitled"}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  supervisor: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow-lg font-semibold text-center min-w-[120px] text-[13px]"
      style={{ background: "linear-gradient(180deg, var(--blue-4), var(--blue-3))", color: "#0a0a0f", boxShadow: "0 4px 14px -4px var(--blue-glow)" }}>
      <Handle type="source" position={Position.Bottom} id="left" style={{ ...handleStyle, left: "25%" }} />
      <Handle type="source" position={Position.Bottom} id="center" style={{ ...handleStyle, left: "50%" }} />
      <Handle type="source" position={Position.Bottom} id="right" style={{ ...handleStyle, left: "75%" }} />
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] opacity-60 mb-0.5">Router</div>
      {data.label}
    </div>
  ),
  agent: ({ data }: { data: { label: string; model: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid var(--emerald-3)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--fg-muted)" }}>Agent</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <div className="text-[10px] mt-0.5" style={{ color: "var(--fg-muted)" }}>{data.model}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  approval: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-center text-[13px]"
      style={{ background: "var(--amber-1)", border: "2px solid var(--amber-3)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--amber-4)" }}>HITL</div>
      <div className="font-medium" style={{ color: "var(--amber-4)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  tool: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid #d97706" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "#fbbf24" }}>Tool</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  knowledge: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid var(--purple-3)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--purple-4)" }}>Knowledge</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  if_else: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid var(--amber-3)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--amber-4)" }}>Condition</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} id="true" style={{ ...handleStyle, left: "30%" }} />
      <Handle type="source" position={Position.Bottom} id="false" style={{ ...handleStyle, left: "70%" }} />
    </div>
  ),
  loop: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid #06b6d4" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "#22d3ee" }}>Loop</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  http: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid var(--blue-3)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--blue-4)" }}>HTTP</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  code: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--bg-canvas)", border: "2px solid var(--border-strong)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--fg-muted)" }}>Code</div>
      <div className="font-medium" style={{ color: "var(--fg-primary)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  start: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--emerald-1)", border: "2px solid var(--emerald-3)" }}>
      <div className="text-[10px] mb-0.5" style={{ color: "var(--emerald-4)" }}>Start</div>
      <div className="font-medium" style={{ color: "var(--emerald-4)" }}>{data.label}</div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  ),
  end: ({ data }: { data: { label: string } }) => (
    <div className="px-4 py-3 rounded-lg shadow min-w-[120px] text-[13px]"
      style={{ background: "var(--red-1)", border: "2px solid var(--red-3)" }}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div className="text-[10px] mb-0.5" style={{ color: "var(--red-4)" }}>End</div>
      <div className="font-medium" style={{ color: "var(--red-4)" }}>{data.label}</div>
    </div>
  ),
};

function GraphCanvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<{ id: string; type: string; data: Record<string, unknown> } | null>(null);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNode({ id: node.id, type: node.type || "default", data: node.data as Record<string, unknown> });
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const handleSave = (nodeId: string, data: Record<string, unknown>) => {
    setNodes((nds) =>
      nds.map((n) => (n.id === nodeId ? { ...n, data } : n))
    );
    setSelectedNode(null);
  };

  return (
    <div className="flex h-full">
      <NodePalette />
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          defaultEdgeOptions={{ style: { stroke: "var(--fg-subtle)", strokeWidth: 2 } }}
          style={{ background: "var(--bg-page)" }}
        >
          <Controls />
          <MiniMap
            style={{ background: "var(--bg-canvas)", border: "1px solid var(--border-subtle)" }}
            maskColor="rgba(0,0,0,0.3)"
          />
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--border-subtle)" />
        </ReactFlow>
        <ConfigPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          onSave={handleSave}
        />
      </div>
    </div>
  );
}

export default function WorkflowsPage() {
  return (
    <div className="flex flex-col h-full">
      <div
        className="flex items-center justify-between px-4 py-2.5 shrink-0"
        style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--bg-canvas)" }}
      >
        <h1 className="text-[15px] font-semibold tracking-tight">Workflow Editor</h1>
        <div className="flex gap-2">
          <button className="btn sm">Save</button>
          <button className="btn sm primary">Run</button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ReactFlowProvider>
          <GraphCanvas />
        </ReactFlowProvider>
      </div>
    </div>
  );
}
