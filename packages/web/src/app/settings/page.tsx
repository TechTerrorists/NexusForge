"use client";

import { useState } from "react";
import { Settings, Key, Shield, Server, Save, Plus, Trash2 } from "lucide-react";

type Section = "general" | "llm" | "security" | "api-keys";

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "General", icon: <Settings size={14} /> },
  { id: "llm", label: "LLM Providers", icon: <Server size={14} /> },
  { id: "security", label: "Security", icon: <Shield size={14} /> },
  { id: "api-keys", label: "API Keys", icon: <Key size={14} /> },
];

const inputStyle = {
  background: "var(--bg-elevated)",
  border: "1px solid var(--border-default)",
  color: "var(--fg-primary)",
};

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<Section>("general");
  const [saved, setSaved] = useState(false);
  const [orgName, setOrgName] = useState("TechTerrorists");
  const [defaultModel, setDefaultModel] = useState("gpt-4o");
  const [maxRuns, setMaxRuns] = useState("10");
  const [logRetention, setLogRetention] = useState("30");

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const renderContent = () => {
    switch (activeSection) {
      case "general":
        return (
          <div className="space-y-5">
            <div>
              <label className="block text-[13px] font-medium mb-1" style={{ color: "var(--fg-secondary)" }}>Organization Name</label>
              <input type="text" value={orgName} onChange={(e) => setOrgName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
                style={{ ...inputStyle, ["--tw-ring-color" as string]: "var(--border-focus)" }} />
            </div>
            <div>
              <label className="block text-[13px] font-medium mb-1" style={{ color: "var(--fg-secondary)" }}>Default LLM Model</label>
              <select value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
                style={{ ...inputStyle, ["--tw-ring-color" as string]: "var(--border-focus)" }}>
                <option value="gpt-4o">GPT-4o</option>
                <option value="gpt-4o-mini">GPT-4o Mini</option>
                <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
                <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-[13px] font-medium mb-1" style={{ color: "var(--fg-secondary)" }}>Max Concurrent Runs</label>
                <input type="number" value={maxRuns} onChange={(e) => setMaxRuns(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
                  style={{ ...inputStyle, ["--tw-ring-color" as string]: "var(--border-focus)" }} />
              </div>
              <div>
                <label className="block text-[13px] font-medium mb-1" style={{ color: "var(--fg-secondary)" }}>Log Retention (days)</label>
                <input type="number" value={logRetention} onChange={(e) => setLogRetention(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
                  style={{ ...inputStyle, ["--tw-ring-color" as string]: "var(--border-focus)" }} />
              </div>
            </div>
          </div>
        );
      case "llm":
        return (
          <div className="space-y-4">
            {["OpenAI", "Anthropic", "Azure OpenAI"].map((name, i) => (
              <div key={name} className="rounded-lg p-4 space-y-3" style={{ border: "1px solid var(--border-subtle)" }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] font-semibold" style={{ color: "var(--fg-primary)" }}>{name}</span>
                    <span className="badge" style={{ color: i < 2 ? "var(--emerald-4)" : "var(--fg-muted)" }}>
                      {i < 2 ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  <button style={{ color: "var(--red-4)" }}><Trash2 size={14} /></button>
                </div>
                <input type="password" placeholder="sk-..." className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none focus:ring-1"
                  style={{ ...inputStyle, ["--tw-ring-color" as string]: "var(--border-focus)" }} />
              </div>
            ))}
            <button className="btn w-full justify-center" style={{ borderStyle: "dashed", color: "var(--fg-muted)" }}>
              <Plus size={14} /> Add Provider
            </button>
          </div>
        );
      case "security":
        return (
          <div className="space-y-4">
            {[
              { label: "Enforce SSO", desc: "Require single sign-on for all users" },
              { label: "Require MFA", desc: "Multi-factor authentication for all accounts" },
              { label: "Audit Logging", desc: "Track all user actions and API calls" },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between py-2">
                <div>
                  <p className="text-[13px] font-medium" style={{ color: "var(--fg-primary)" }}>{item.label}</p>
                  <p className="text-[12px]" style={{ color: "var(--fg-muted)" }}>{item.desc}</p>
                </div>
                <div className="w-9 h-5 rounded-full relative cursor-pointer" style={{ background: "var(--bg-overlay)" }}>
                  <div className="w-4 h-4 bg-white rounded-full absolute top-0.5 left-0.5 transition-transform" />
                </div>
              </div>
            ))}
          </div>
        );
      case "api-keys":
        return (
          <div className="space-y-3">
            {[
              { name: "Production", key: "nf_prod_****...x8k2", date: "2025-12-01" },
              { name: "Development", key: "nf_dev_****...m3p9", date: "2025-11-15" },
            ].map((k) => (
              <div key={k.name} className="flex items-center justify-between p-3 rounded-lg" style={{ border: "1px solid var(--border-subtle)" }}>
                <div>
                  <p className="text-[13px] font-medium" style={{ color: "var(--fg-primary)" }}>{k.name}</p>
                  <p className="text-[11px] font-mono" style={{ color: "var(--fg-muted)" }}>{k.key}</p>
                  <p className="text-[11px] mt-0.5" style={{ color: "var(--fg-muted)" }}>Created {k.date}</p>
                </div>
                <button style={{ color: "var(--red-4)" }}><Trash2 size={14} /></button>
              </div>
            ))}
            <button className="btn w-full justify-center" style={{ borderStyle: "dashed", color: "var(--fg-muted)" }}>
              <Plus size={14} /> Generate New Key
            </button>
          </div>
        );
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <button
          onClick={handleSave}
          className="btn"
          style={{
            background: saved ? "var(--emerald-3)" : "var(--blue-3)",
            color: "#0a0a0f",
            borderColor: saved ? "var(--emerald-3)" : "var(--blue-3)",
          }}
        >
          <Save size={14} />
          {saved ? "Saved!" : "Save Changes"}
        </button>
      </div>

      <div className="flex gap-6">
        <nav className="w-44 shrink-0">
          <div className="space-y-0.5">
            {SECTIONS.map((section) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors text-left"
                style={{
                  background: activeSection === section.id ? "rgba(110,161,240,0.1)" : "transparent",
                  color: activeSection === section.id ? "var(--blue-4)" : "var(--fg-muted)",
                }}
              >
                {section.icon}
                {section.label}
              </button>
            ))}
          </div>
        </nav>

        <div className="flex-1 rounded-lg p-5" style={{ background: "var(--bg-canvas)", border: "1px solid var(--border-subtle)" }}>
          <h3 className="text-[15px] font-semibold mb-4" style={{ color: "var(--fg-primary)" }}>
            {SECTIONS.find((s) => s.id === activeSection)?.label}
          </h3>
          {renderContent()}
        </div>
      </div>
    </div>
  );
}
