"use client";

import { useState, useEffect } from "react";
import { X, Save, ChevronDown } from "lucide-react";

interface NodeData {
  label?: string;
  model?: string;
  tools?: string[];
  prompt?: string;
  toolType?: string;
  config?: Record<string, unknown>;
  topK?: number;
  threshold?: number;
  condition?: string;
  maxIterations?: number;
  collection?: string;
  method?: string;
  url?: string;
  headers?: Record<string, string>;
  language?: string;
  code?: string;
  [key: string]: unknown;
}

interface ConfigPanelProps {
  node: {
    id: string;
    type: string;
    data: NodeData;
  } | null;
  onClose: () => void;
  onSave: (nodeId: string, data: NodeData) => void;
}

const AVAILABLE_TOOLS = [
  "web_search",
  "arxiv",
  "summarize",
  "github",
  "code_analysis",
  "sql_query",
  "chart_gen",
  "pandas",
  "email_send",
  "template",
  "knowledge_base",
  "sast",
  "dependency_check",
  "secret_scan",
  "zendesk",
  "crm",
];

const MODELS = [
  "gpt-4o",
  "gpt-4o-mini",
  "claude-sonnet-4-20250514",
  "claude-3-haiku-20240307",
  "llama-3.1-70b",
  "mixtral-8x7b",
];

const LABELS: Record<string, string> = {
  agent: "Agent Configuration",
  tool: "Tool Configuration",
  knowledge: "Knowledge Base Configuration",
  if_else: "Condition Configuration",
  loop: "Loop Configuration",
  http: "HTTP Request Configuration",
  code: "Code Execution Configuration",
  start: "Start Node",
  end: "End Node",
  default: "Node Configuration",
};

export default function ConfigPanel({ node, onClose, onSave }: ConfigPanelProps) {
  const [formData, setFormData] = useState<NodeData>({});

  useEffect(() => {
    if (node) {
      setFormData({ ...node.data });
    }
  }, [node]);

  if (!node) return null;

  const nodeType = node.type || "default";
  const title = LABELS[nodeType] || LABELS.default;

  const updateField = (key: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const toggleTool = (tool: string) => {
    const tools = formData.tools || [];
    if (tools.includes(tool)) {
      updateField(
        "tools",
        tools.filter((t) => t !== tool)
      );
    } else {
      updateField("tools", [...tools, tool]);
    }
  };

  const renderFields = () => {
    switch (nodeType) {
      case "agent":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Model">
              <select
                value={(formData.model as string) || ""}
                onChange={(e) => updateField("model", e.target.value)}
                className={inputClass}
              >
                {MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </FieldGroup>
            <FieldGroup label="Tools">
              <div className="flex flex-wrap gap-1">
                {AVAILABLE_TOOLS.map((tool) => (
                  <button
                    key={tool}
                    onClick={() => toggleTool(tool)}
                    className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                      (formData.tools || []).includes(tool)
                        ? "bg-brand-100 border-brand-400 text-brand-700 dark:bg-brand-900/30"
                        : "bg-gray-50 border-gray-200 text-gray-500 dark:bg-gray-700 dark:border-gray-600"
                    }`}
                  >
                    {tool}
                  </button>
                ))}
              </div>
            </FieldGroup>
            <FieldGroup label="System Prompt">
              <textarea
                value={(formData.prompt as string) || ""}
                onChange={(e) => updateField("prompt", e.target.value)}
                placeholder="You are a helpful assistant..."
                rows={4}
                className={inputClass + " resize-none"}
              />
            </FieldGroup>
          </>
        );

      case "tool":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Tool Type">
              <select
                value={(formData.toolType as string) || "function"}
                onChange={(e) => updateField("toolType", e.target.value)}
                className={inputClass}
              >
                <option value="function">Function</option>
                <option value="api">API Call</option>
                <option value="mcp">MCP Server</option>
                <option value="webhook">Webhook</option>
              </select>
            </FieldGroup>
            <FieldGroup label="Configuration (JSON)">
              <textarea
                value={JSON.stringify(formData.config || {}, null, 2)}
                onChange={(e) => {
                  try {
                    updateField("config", JSON.parse(e.target.value));
                  } catch {
                    // invalid JSON, ignore
                  }
                }}
                rows={4}
                className={inputClass + " resize-none font-mono text-xs"}
              />
            </FieldGroup>
          </>
        );

      case "knowledge":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Top K Results">
              <input
                type="number"
                value={(formData.topK as number) || 5}
                onChange={(e) => updateField("topK", parseInt(e.target.value))}
                min={1}
                max={20}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Similarity Threshold">
              <input
                type="number"
                value={(formData.threshold as number) || 0.7}
                onChange={(e) =>
                  updateField("threshold", parseFloat(e.target.value))
                }
                min={0}
                max={1}
                step={0.05}
                className={inputClass}
              />
            </FieldGroup>
          </>
        );

      case "if_else":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Condition Expression">
              <textarea
                value={(formData.condition as string) || ""}
                onChange={(e) => updateField("condition", e.target.value)}
                placeholder="output.contains('error')"
                rows={3}
                className={inputClass + " resize-none font-mono text-xs"}
              />
            </FieldGroup>
          </>
        );

      case "loop":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Max Iterations">
              <input
                type="number"
                value={(formData.maxIterations as number) || 10}
                onChange={(e) =>
                  updateField("maxIterations", parseInt(e.target.value))
                }
                min={1}
                max={100}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Collection Variable">
              <input
                type="text"
                value={(formData.collection as string) || ""}
                onChange={(e) => updateField("collection", e.target.value)}
                placeholder="items"
                className={inputClass}
              />
            </FieldGroup>
          </>
        );

      case "http":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Method">
              <select
                value={(formData.method as string) || "GET"}
                onChange={(e) => updateField("method", e.target.value)}
                className={inputClass}
              >
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="PATCH">PATCH</option>
                <option value="DELETE">DELETE</option>
              </select>
            </FieldGroup>
            <FieldGroup label="URL">
              <input
                type="text"
                value={(formData.url as string) || ""}
                onChange={(e) => updateField("url", e.target.value)}
                placeholder="https://api.example.com/endpoint"
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Headers (JSON)">
              <textarea
                value={JSON.stringify(formData.headers || {}, null, 2)}
                onChange={(e) => {
                  try {
                    updateField("headers", JSON.parse(e.target.value));
                  } catch {
                    // invalid JSON
                  }
                }}
                rows={3}
                className={inputClass + " resize-none font-mono text-xs"}
              />
            </FieldGroup>
          </>
        );

      case "code":
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Language">
              <select
                value={(formData.language as string) || "python"}
                onChange={(e) => updateField("language", e.target.value)}
                className={inputClass}
              >
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="typescript">TypeScript</option>
                <option value="bash">Bash</option>
              </select>
            </FieldGroup>
            <FieldGroup label="Code">
              <textarea
                value={(formData.code as string) || ""}
                onChange={(e) => updateField("code", e.target.value)}
                placeholder="def process(input_data):"
                rows={8}
                className={inputClass + " resize-none font-mono text-xs"}
              />
            </FieldGroup>
          </>
        );

      case "start":
      case "end":
        return (
          <FieldGroup label="Name">
            <input
              type="text"
              value={(formData.label as string) || ""}
              onChange={(e) => updateField("label", e.target.value)}
              className={inputClass}
            />
          </FieldGroup>
        );

      default:
        return (
          <>
            <FieldGroup label="Name">
              <input
                type="text"
                value={(formData.label as string) || ""}
                onChange={(e) => updateField("label", e.target.value)}
                className={inputClass}
              />
            </FieldGroup>
            <FieldGroup label="Custom Properties (JSON)">
              <textarea
                value={JSON.stringify(formData, null, 2)}
                onChange={(e) => {
                  try {
                    setFormData(JSON.parse(e.target.value));
                  } catch {
                    // invalid JSON
                  }
                }}
                rows={6}
                className={inputClass + " resize-none font-mono text-xs"}
              />
            </FieldGroup>
          </>
        );
    }
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1";

  return (
    <div className="w-72 shrink-0 overflow-y-auto" style={{ borderLeft: "1px solid var(--border-subtle)", background: "var(--bg-canvas)" }}>
      <div className="flex items-center justify-between px-3 py-2.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <h3 className="text-[13px] font-medium" style={{ color: "var(--fg-primary)" }}>{title}</h3>
        <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
          <X size={14} style={{ color: "var(--fg-muted)" }} />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="text-xs text-gray-400 font-mono bg-gray-50 dark:bg-gray-700/50 rounded px-2 py-1">
          ID: {node.id}
        </div>

        {renderFields()}

        <div className="flex gap-2 pt-2">
          <button
            onClick={() => onSave(node.id, formData)}
            className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700"
          >
            <Save size={14} />
            Save
          </button>
          <button
            onClick={onClose}
            className="px-3 py-2 border rounded-lg text-sm text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function FieldGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--fg-muted)" }}>
        {label}
      </label>
      {children}
    </div>
  );
}
