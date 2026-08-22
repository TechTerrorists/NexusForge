"use client";

import { useState } from "react";
import { Plus, Database, Search, Upload, FileText, Layers, Trash2 } from "lucide-react";

interface KB {
  id: string;
  name: string;
  docCount: number;
  chunkCount: number;
  embeddingModel: string;
  description: string;
  lastUpdated: string;
}

const DEMO_KB: KB[] = [
  { id: "kb1", name: "Product Documentation", docCount: 234, chunkCount: 4812, embeddingModel: "text-embedding-3-small", description: "Full product docs, API references, and user guides.", lastUpdated: "2 hours ago" },
  { id: "kb2", name: "Company Policies", docCount: 47, chunkCount: 891, embeddingModel: "text-embedding-3-small", description: "HR policies, compliance rules, and internal procedures.", lastUpdated: "1 day ago" },
  { id: "kb3", name: "Sales Playbooks", docCount: 89, chunkCount: 2340, embeddingModel: "text-embedding-3-large", description: "Battle cards, objection handling, and competitive intel.", lastUpdated: "3 days ago" },
  { id: "kb4", name: "Codebase Embeddings", docCount: 1562, chunkCount: 28934, embeddingModel: "voyage-code-3", description: "Embedded source code and architecture documentation.", lastUpdated: "6 hours ago" },
  { id: "kb5", name: "Support Tickets Archive", docCount: 3421, chunkCount: 15200, embeddingModel: "text-embedding-3-small", description: "Historical support tickets with resolutions and metadata.", lastUpdated: "12 hours ago" },
];

export default function KnowledgePage() {
  const [query, setQuery] = useState("");

  const filtered = DEMO_KB.filter(
    (kb) =>
      kb.name.toLowerCase().includes(query.toLowerCase()) ||
      kb.description.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Knowledge Bases</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
            {DEMO_KB.length} bases · {DEMO_KB.reduce((s, k) => s + k.chunkCount, 0).toLocaleString()} chunks
          </p>
        </div>
        <button className="btn primary">
          <Plus size={14} />
          New Knowledge Base
        </button>
      </div>

      <div className="relative max-w-md">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--fg-muted)" }} />
        <input
          type="text"
          placeholder="Search knowledge bases..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full pl-8 pr-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-default)",
            color: "var(--fg-primary)",
            ["--tw-ring-color" as string]: "var(--border-focus)",
          }}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((kb) => (
          <div
            key={kb.id}
            className="rounded-lg transition-shadow hover:shadow-md"
            style={{ background: "var(--bg-canvas)", border: "1px solid var(--border-subtle)" }}
          >
            <div className="p-4">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: "var(--purple-1)", border: "1px solid var(--purple-2)" }}
                  >
                    <Database size={16} style={{ color: "var(--purple-4)" }} />
                  </div>
                  <div>
                    <h3 className="text-[13px] font-semibold" style={{ color: "var(--fg-primary)" }}>{kb.name}</h3>
                    <p className="text-[11px]" style={{ color: "var(--fg-muted)" }}>{kb.embeddingModel}</p>
                  </div>
                </div>
              </div>

              <p className="text-[13px] mb-3" style={{ color: "var(--fg-muted)" }}>{kb.description}</p>

              <div className="grid grid-cols-2 gap-2 mb-3">
                <div className="rounded p-2 text-center" style={{ background: "var(--bg-elevated)" }}>
                  <div className="text-lg font-bold flex items-center justify-center gap-1" style={{ color: "var(--fg-primary)" }}>
                    <FileText size={14} style={{ color: "var(--fg-muted)" }} />
                    {kb.docCount.toLocaleString()}
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--fg-muted)" }}>Documents</div>
                </div>
                <div className="rounded p-2 text-center" style={{ background: "var(--bg-elevated)" }}>
                  <div className="text-lg font-bold flex items-center justify-center gap-1" style={{ color: "var(--fg-primary)" }}>
                    <Layers size={14} style={{ color: "var(--fg-muted)" }} />
                    {kb.chunkCount.toLocaleString()}
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--fg-muted)" }}>Chunks</div>
                </div>
              </div>

              <p className="text-[11px] mb-3" style={{ color: "var(--fg-muted)" }}>
                Updated {kb.lastUpdated}
              </p>

              <div className="flex gap-2 pt-3" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <button className="flex-1 btn sm justify-center" style={{ color: "var(--blue-4)" }}>
                  <Search size={12} />
                  Query
                </button>
                <button className="flex-1 btn sm justify-center" style={{ color: "var(--emerald-4)" }}>
                  <Upload size={12} />
                  Upload
                </button>
                <button className="btn sm" style={{ color: "var(--fg-muted)" }}>
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
