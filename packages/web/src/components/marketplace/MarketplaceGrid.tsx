"use client";

import { Badge } from "@/components/ui";

interface Template {
  id: string;
  name: string;
  description: string;
  domain: string;
  installs: number;
  author: string;
}

const DEMO_TEMPLATES: Template[] = [
  { id: "t1", name: "Sales Outreach Pipeline", description: "Automated lead research, email drafting, and follow-up scheduling.", domain: "sales_ops", installs: 234, author: "NexusForge" },
  { id: "t2", name: "Support Ticket Triage", description: "Classify, prioritize, and route incoming support tickets.", domain: "support_ops", installs: 189, author: "NexusForge" },
  { id: "t3", name: "Code Review Assistant", description: "Automated PR review with security scanning and suggestions.", domain: "engineering", installs: 312, author: "Community" },
  { id: "t4", name: "Financial Reconciliation", description: "Match transactions across accounts and flag discrepancies.", domain: "finance", installs: 87, author: "NexusForge" },
];

const DOMAIN_COLORS: Record<string, string> = {
  sales_ops: "blue",
  support_ops: "amber",
  engineering: "emerald",
  finance: "purple",
};

export default function MarketplaceGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {DEMO_TEMPLATES.map((tpl) => (
        <div
          key={tpl.id}
          className="rounded-lg p-4 transition-shadow hover:shadow-md"
          style={{ background: "var(--bg-canvas)", border: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-start justify-between mb-2">
            <h3 className="text-[13px] font-semibold" style={{ color: "var(--fg-primary)" }}>
              {tpl.name}
            </h3>
            <Badge variant={(DOMAIN_COLORS[tpl.domain] as "blue" | "purple" | "emerald" | "amber") || "default"}>
              {tpl.domain}
            </Badge>
          </div>
          <p className="text-[12px] mb-3" style={{ color: "var(--fg-muted)" }}>
            {tpl.description}
          </p>
          <div className="flex items-center justify-between" style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "8px" }}>
            <span className="text-[11px]" style={{ color: "var(--fg-muted)" }}>
              by {tpl.author}
            </span>
            <span className="text-[11px]" style={{ color: "var(--fg-muted)" }}>
              {tpl.installs} installs
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
