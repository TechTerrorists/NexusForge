"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Key, Loader2, Save, Server, Settings, Shield } from "lucide-react";
import { api } from "@/lib/nexus";

type Section = "general" | "llm" | "security" | "api-keys";
type Adapter = "openai-compatible" | "anthropic";
type LLMSettings = {
  provider: string;
  adapter: Adapter;
  endpoint: string;
  model: string;
  api_key_configured: boolean;
  api_key_hint: string | null;
  source: string;
};

const SECTIONS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: "general", label: "General", icon: <Settings size={14} /> },
  { id: "llm", label: "LLM Provider", icon: <Server size={14} /> },
  { id: "security", label: "Security", icon: <Shield size={14} /> },
  { id: "api-keys", label: "API Keys", icon: <Key size={14} /> },
];

const inputStyle = {
  background: "var(--bg-elevated)",
  border: "1px solid var(--border-default)",
  color: "var(--fg-primary)",
};

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<Section>("llm");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [orgName, setOrgName] = useState("TechTerrorists");
  const [maxRuns, setMaxRuns] = useState("10");
  const [logRetention, setLogRetention] = useState("30");
  const [provider, setProvider] = useState("OpenCode Zen");
  const [adapter, setAdapter] = useState<Adapter>("openai-compatible");
  const [endpoint, setEndpoint] = useState("https://opencode.ai/zen/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);
  const [apiKeyHint, setApiKeyHint] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [clearApiKey, setClearApiKey] = useState(false);

  useEffect(() => {
    api<LLMSettings>("/api/v1/settings/llm")
      .then((settings) => {
        setProvider(settings.provider);
        setAdapter(settings.adapter);
        setEndpoint(settings.endpoint);
        setModel(settings.model);
        setApiKeyConfigured(settings.api_key_configured);
        setApiKeyHint(settings.api_key_hint);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load settings"))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    if (activeSection !== "llm") {
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
      return;
    }
    if (!provider.trim() || !endpoint.trim() || !model.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const settings = await api<LLMSettings>("/api/v1/settings/llm", {
        method: "PUT",
        body: JSON.stringify({
          provider: provider.trim(),
          adapter,
          endpoint: endpoint.trim(),
          model: model.trim(),
          api_key: apiKey.trim() || null,
          clear_api_key: clearApiKey,
        }),
      });
      setApiKey("");
      setClearApiKey(false);
      setApiKeyConfigured(settings.api_key_configured);
      setApiKeyHint(settings.api_key_hint);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save settings");
    } finally {
      setSaving(false);
    }
  }

  function renderLlmSettings() {
    if (loading) return <div className="py-12 grid place-items-center"><Loader2 className="animate-spin" size={20} /></div>;
    return <div className="space-y-5">
      <div className="rounded-lg p-4 text-[12px]" style={{ background: "var(--blue-1)", color: "var(--fg-secondary)" }}>
        Changes apply immediately to new plans and the next worker step. OpenAI-compatible supports OpenAI, OpenRouter, Groq, Together, Ollama, LM Studio, vLLM, and compatible gateways.
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>Provider name<input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="OpenRouter" className="block w-full mt-1 px-3 py-2 rounded-lg" style={inputStyle} /></label>
        <label className="text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>API protocol<select value={adapter} onChange={(event) => setAdapter(event.target.value as Adapter)} className="block w-full mt-1 px-3 py-2 rounded-lg" style={inputStyle}><option value="openai-compatible">OpenAI-compatible</option><option value="anthropic">Anthropic native</option></select></label>
      </div>
      <label className="block text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>Endpoint<input type="url" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://api.provider.com/v1" className="block w-full mt-1 px-3 py-2 rounded-lg font-mono text-[12px]" style={inputStyle} /></label>
      <label className="block text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>Model<input value={model} onChange={(event) => setModel(event.target.value)} placeholder="provider/model-name" className="block w-full mt-1 px-3 py-2 rounded-lg font-mono text-[12px]" style={inputStyle} /></label>
      <div>
        <label className="block text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>API key</label>
        <div className="relative mt-1">
          <input type={showApiKey ? "text" : "password"} value={apiKey} onChange={(event) => { setApiKey(event.target.value); setClearApiKey(false); }} placeholder={apiKeyConfigured ? `${apiKeyHint || "••••"} configured — leave blank to keep` : "Enter provider API key"} className="w-full px-3 py-2 pr-10 rounded-lg font-mono text-[12px]" style={inputStyle} />
          <button type="button" onClick={() => setShowApiKey((value) => !value)} className="absolute right-3 top-2.5" style={{ color: "var(--fg-muted)" }} aria-label={showApiKey ? "Hide API key" : "Show API key"}>{showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px]" style={{ color: "var(--fg-muted)" }}>
          <span>The key is encrypted at rest; only a masked hint is returned by the API.</span>
          {apiKeyConfigured && <button type="button" onClick={() => { setClearApiKey(true); setApiKey(""); }} style={{ color: clearApiKey ? "var(--red-4)" : "var(--fg-muted)" }}>{clearApiKey ? "Key will be removed on save" : "Remove saved key"}</button>}
        </div>
      </div>
    </div>;
  }

  function renderContent() {
    if (activeSection === "llm") return renderLlmSettings();
    if (activeSection === "general") return <div className="space-y-5">
      <label className="block text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>Organization Name<input value={orgName} onChange={(event) => setOrgName(event.target.value)} className="block w-full mt-1 px-3 py-2 rounded-lg" style={inputStyle} /></label>
      <div className="grid grid-cols-2 gap-4">
        <label className="text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>Max Concurrent Runs<input type="number" value={maxRuns} onChange={(event) => setMaxRuns(event.target.value)} className="block w-full mt-1 px-3 py-2 rounded-lg" style={inputStyle} /></label>
        <label className="text-[13px] font-medium" style={{ color: "var(--fg-secondary)" }}>Log Retention (days)<input type="number" value={logRetention} onChange={(event) => setLogRetention(event.target.value)} className="block w-full mt-1 px-3 py-2 rounded-lg" style={inputStyle} /></label>
      </div>
    </div>;
    return <div className="py-12 text-center text-[13px]" style={{ color: "var(--fg-muted)" }}>This section is managed by deployment policy.</div>;
  }

  return <div className="p-6 space-y-6">
    <div className="flex items-center justify-between">
      <div><h1 className="text-xl font-semibold tracking-tight">Settings</h1><p className="text-[12px] mt-1" style={{ color: "var(--fg-muted)" }}>Runtime configuration—no container restart required.</p></div>
      <button onClick={handleSave} disabled={saving || loading} className="btn" style={{ background: saved ? "var(--emerald-3)" : "var(--blue-3)", color: "#0a0a0f", borderColor: saved ? "var(--emerald-3)" : "var(--blue-3)" }}>{saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}{saved ? "Saved!" : "Save Changes"}</button>
    </div>
    {error && <div className="rounded-lg p-3 text-[12px]" style={{ background: "rgba(248,113,113,.1)", color: "var(--red-4)" }}>{error}</div>}
    <div className="flex gap-6">
      <nav className="w-44 shrink-0"><div className="space-y-0.5">{SECTIONS.map((section) => <button key={section.id} onClick={() => setActiveSection(section.id)} className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-left" style={{ background: activeSection === section.id ? "rgba(110,161,240,0.1)" : "transparent", color: activeSection === section.id ? "var(--blue-4)" : "var(--fg-muted)" }}>{section.icon}{section.label}</button>)}</div></nav>
      <div className="flex-1 rounded-lg p-5" style={{ background: "var(--bg-canvas)", border: "1px solid var(--border-subtle)" }}><h3 className="text-[15px] font-semibold mb-4">{SECTIONS.find((section) => section.id === activeSection)?.label}</h3>{renderContent()}</div>
    </div>
  </div>;
}
