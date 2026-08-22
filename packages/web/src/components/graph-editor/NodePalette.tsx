"use client";

import { useReactFlow } from "@xyflow/react";
import {
  Bot,
  Wrench,
  Database,
  GitBranch,
  Repeat,
  Globe,
  Code,
  Play,
  Circle,
  ChevronDown,
  ChevronRight,
  GripVertical,
} from "lucide-react";
import { useState, useCallback } from "react";

interface PaletteItem {
  type: string;
  label: string;
  icon: React.ReactNode;
  category: string;
  color: string;
  defaults: Record<string, unknown>;
}

const PALETTE_ITEMS: Record<string, PaletteItem[]> = {
  Agent: [
    {
      type: "agent",
      label: "Agent",
      icon: <Bot size={16} />,
      category: "Agent",
      color: "border-green-400 bg-green-50 dark:bg-green-900/20",
      defaults: { label: "New Agent", model: "gpt-4o-mini", tools: [], prompt: "" },
    },
  ],
  Tool: [
    {
      type: "tool",
      label: "Tool",
      icon: <Wrench size={16} />,
      category: "Tool",
      color: "border-orange-400 bg-orange-50 dark:bg-orange-900/20",
      defaults: { label: "New Tool", toolType: "function", config: {} },
    },
  ],
  Knowledge: [
    {
      type: "knowledge",
      label: "Knowledge Base",
      icon: <Database size={16} />,
      category: "Knowledge",
      color: "border-purple-400 bg-purple-50 dark:bg-purple-900/20",
      defaults: { label: "Knowledge Base", topK: 5, threshold: 0.7 },
    },
  ],
  Workflow: [
    {
      type: "if_else",
      label: "If / Else",
      icon: <GitBranch size={16} />,
      category: "Workflow",
      color: "border-yellow-400 bg-yellow-50 dark:bg-yellow-900/20",
      defaults: { label: "If / Else", condition: "" },
    },
    {
      type: "loop",
      label: "Loop",
      icon: <Repeat size={16} />,
      category: "Workflow",
      color: "border-cyan-400 bg-cyan-50 dark:bg-cyan-900/20",
      defaults: { label: "Loop", maxIterations: 10, collection: "" },
    },
    {
      type: "http",
      label: "HTTP Request",
      icon: <Globe size={16} />,
      category: "Workflow",
      color: "border-blue-400 bg-blue-50 dark:bg-blue-900/20",
      defaults: { label: "HTTP Request", method: "GET", url: "", headers: {} },
    },
    {
      type: "code",
      label: "Code Execution",
      icon: <Code size={16} />,
      category: "Workflow",
      color: "border-gray-400 bg-gray-50 dark:bg-gray-700/50",
      defaults: { label: "Code", language: "python", code: "" },
    },
  ],
  Control: [
    {
      type: "start",
      label: "Start",
      icon: <Play size={16} />,
      category: "Control",
      color: "border-green-500 bg-green-100 dark:bg-green-900/30",
      defaults: { label: "Start" },
    },
    {
      type: "end",
      label: "End",
      icon: <Circle size={16} />,
      category: "Control",
      color: "border-red-400 bg-red-50 dark:bg-red-900/20",
      defaults: { label: "End" },
    },
  ],
};

export default function NodePalette() {
  const { getNodes, setNodes } = useReactFlow();
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    Agent: true,
    Tool: true,
    Knowledge: true,
    Workflow: true,
    Control: true,
  });

  const toggleCategory = (category: string) => {
    setOpenCategories((prev) => ({ ...prev, [category]: !prev[category] }));
  };

  const addNode = useCallback(
    (item: PaletteItem) => {
      const nodes = getNodes();
      const maxX = nodes.reduce((max, n) => Math.max(max, n.position.x), 0);
      const nodeType = ["start", "end", "agent", "tool", "knowledge", "if_else", "loop", "http", "code"].includes(item.type)
        ? item.type
        : "default";
      const newNode = {
        id: `${item.type}_${Date.now()}`,
        type: nodeType,
        position: { x: maxX + 200, y: 200 },
        data: { label: item.defaults.label, model: item.defaults.model, tools: item.defaults.tools },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [getNodes, setNodes]
  );

  return (
    <div className="w-52 shrink-0 overflow-y-auto" style={{ borderRight: "1px solid var(--border-subtle)", background: "var(--bg-canvas)" }}>
      <div className="px-3 py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3 className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--fg-muted)", fontFamily: "var(--font-mono)" }}>
          Node Palette
        </h3>
      </div>
      <div className="p-2">
        {Object.entries(PALETTE_ITEMS).map(([category, items]) => (
          <div key={category} className="mb-1">
              <button
                onClick={() => toggleCategory(category)}
                className="w-full flex items-center gap-1 px-2 py-1.5 text-[11px] font-medium rounded"
                style={{ color: "var(--fg-muted)" }}
              >
              {openCategories[category] ? (
                <ChevronDown size={12} />
              ) : (
                <ChevronRight size={12} />
              )}
              {category}
            </button>
            {openCategories[category] && (
              <div className="space-y-1 mt-0.5">
                {items.map((item) => (
                  <div
                    key={item.type}
                    onClick={() => addNode(item)}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("application/reactflow", item.type);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded border text-xs cursor-grab active:cursor-grabbing hover:shadow-sm transition-shadow ${item.color}`}
                  >
                    <GripVertical size={10} className="text-gray-300 shrink-0" />
                    {item.icon}
                    <span className="font-medium">{item.label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
