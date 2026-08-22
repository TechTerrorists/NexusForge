"use client";

import { useState } from "react";
import { Search, Star, Download, Tag, User, CheckCircle, ExternalLink } from "lucide-react";

interface Template {
  id: string;
  name: string;
  domain: string;
  description: string;
  installs: number;
  rating: number;
  author: string;
  tags: string[];
  verified: boolean;
}

const DEMO_TEMPLATES: Template[] = [
  { id: "t1", name: "Customer Support Pipeline", domain: "Support", description: "Multi-agent pipeline for ticket triage, escalation, and resolution with RAG.", installs: 2341, rating: 4.8, author: "nexusforge", tags: ["support", "rag", "multi-agent"], verified: true },
  { id: "t2", name: "Code Review Assistant", domain: "Engineering", description: "Automated PR review with linting, security scanning, and suggestion generation.", installs: 1876, rating: 4.7, author: "nexusforge", tags: ["code", "review", "github"], verified: true },
  { id: "t3", name: "Sales Outreach Engine", domain: "Sales", description: "Personalized email generation from CRM data with follow-up scheduling.", installs: 987, rating: 4.5, author: "community", tags: ["sales", "email", "crm"], verified: false },
  { id: "t4", name: "Document Processor", domain: "Data", description: "OCR, extraction, and structuring of PDFs, images, and scanned documents.", installs: 1543, rating: 4.6, author: "nexusforge", tags: ["ocr", "pdf", "extraction"], verified: true },
  { id: "t5", name: "Research Synthesizer", domain: "Research", description: "Multi-source research aggregation with citation tracking and report generation.", installs: 654, rating: 4.3, author: "community", tags: ["research", "papers"], verified: false },
  { id: "t6", name: "Workflow Debugger", domain: "DevTools", description: "Step-through debugger for agent workflows with breakpoints and variable inspection.", installs: 432, rating: 4.9, author: "nexusforge", tags: ["debug", "devtools"], verified: true },
  { id: "t7", name: "Data Pipeline Orchestrator", domain: "Data", description: "ETL workflow with validation, transformation, and loading across multiple sources.", installs: 1102, rating: 4.4, author: "community", tags: ["etl", "data"], verified: false },
  { id: "t8", name: "Meeting Summarizer", domain: "Productivity", description: "Transcribes meetings, extracts action items, and distributes follow-ups.", installs: 789, rating: 4.2, author: "community", tags: ["meetings", "summary"], verified: false },
  { id: "t9", name: "Threat Intelligence Analyzer", domain: "Security", description: "Correlates threat feeds, CVEs, and SIEM alerts into actionable reports.", installs: 321, rating: 4.7, author: "nexusforge", tags: ["security", "siem"], verified: true },
];

const DOMAINS = ["All", ...Array.from(new Set(DEMO_TEMPLATES.map((t) => t.domain)))];

export default function MarketplacePage() {
  const [search, setSearch] = useState("");
  const [selectedDomain, setSelectedDomain] = useState("All");
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());

  const filtered = DEMO_TEMPLATES.filter((t) => {
    const matchSearch = t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.description.toLowerCase().includes(search.toLowerCase()) ||
      t.tags.some((tag) => tag.toLowerCase().includes(search.toLowerCase()));
    const matchDomain = selectedDomain === "All" || t.domain === selectedDomain;
    return matchSearch && matchDomain;
  });

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Marketplace</h1>
          <p className="text-[13px] mt-0.5" style={{ color: "var(--fg-muted)" }}>
            {DEMO_TEMPLATES.length} templates available
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--fg-muted)" }} />
          <input
            type="text"
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-default)",
              color: "var(--fg-primary)",
              ["--tw-ring-color" as string]: "var(--border-focus)",
            }}
          />
        </div>
        <div className="flex gap-1">
          {DOMAINS.map((domain) => (
            <button
              key={domain}
              onClick={() => setSelectedDomain(domain)}
              className="px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors"
              style={{
                background: selectedDomain === domain ? "var(--blue-3)" : "var(--bg-elevated)",
                color: selectedDomain === domain ? "#0a0a0f" : "var(--fg-muted)",
              }}
            >
              {domain}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((t) => (
          <div
            key={t.id}
            className="rounded-lg flex flex-col transition-shadow hover:shadow-md"
            style={{ background: "var(--bg-canvas)", border: "1px solid var(--border-subtle)" }}
          >
            <div className="p-4 flex-1">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="flex items-center gap-1.5">
                    <h3 className="text-[13px] font-semibold" style={{ color: "var(--fg-primary)" }}>{t.name}</h3>
                    {t.verified && <CheckCircle size={13} style={{ color: "var(--blue-4)" }} />}
                  </div>
                  <span
                    className="inline-block mt-1 px-2 py-0.5 rounded text-[10px]"
                    style={{ background: "var(--bg-elevated)", color: "var(--fg-muted)" }}
                  >
                    {t.domain}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[13px]" style={{ color: "var(--fg-secondary)" }}>
                  <Star size={13} style={{ color: "var(--amber-4)" }} fill="var(--amber-4)" />
                  {t.rating}
                </div>
              </div>

              <p className="text-[13px] mb-3" style={{ color: "var(--fg-muted)" }}>{t.description}</p>

              <div className="flex flex-wrap gap-1 mb-3">
                {t.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]"
                    style={{ background: "var(--bg-elevated)", color: "var(--fg-muted)" }}
                  >
                    <Tag size={9} />
                    {tag}
                  </span>
                ))}
              </div>

              <div className="flex items-center justify-between text-[11px]" style={{ color: "var(--fg-muted)" }}>
                <div className="flex items-center gap-1"><User size={11} />{t.author}</div>
                <div className="flex items-center gap-1"><Download size={11} />{t.installs.toLocaleString()}</div>
              </div>
            </div>

            <div className="p-4 flex gap-2" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <button
                onClick={() => {
                  setInstalledIds((prev) => {
                    const next = new Set(prev);
                    next.has(t.id) ? next.delete(t.id) : next.add(t.id);
                    return next;
                  });
                }}
                className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors"
                style={{
                  background: installedIds.has(t.id) ? "var(--emerald-1)" : "var(--blue-3)",
                  color: installedIds.has(t.id) ? "var(--emerald-4)" : "#0a0a0f",
                }}
              >
                <Download size={13} />
                {installedIds.has(t.id) ? "Installed" : "Install"}
              </button>
              <button
                className="px-3 py-1.5 rounded-lg text-[13px]"
                style={{ border: "1px solid var(--border-default)", color: "var(--fg-muted)" }}
              >
                <ExternalLink size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12">
          <Search size={40} className="mx-auto mb-3 opacity-30" style={{ color: "var(--fg-muted)" }} />
          <p className="text-[15px] font-medium" style={{ color: "var(--fg-secondary)" }}>No templates found</p>
          <p className="text-[13px]" style={{ color: "var(--fg-muted)" }}>Try a different search or domain filter.</p>
        </div>
      )}
    </div>
  );
}
