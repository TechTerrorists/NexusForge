"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Zap } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const endpoint = mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const body = mode === "login"
        ? { email, password }
        : { email, username, password };

      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Authentication failed");
        setLoading(false);
        return;
      }

      const data = await res.json();
      localStorage.setItem("nf_token", data.access_token);
      localStorage.setItem("nf_refresh", data.refresh_token);
      localStorage.setItem("nf_user", JSON.stringify({ id: data.user_id, role: data.role }));
      router.push("/");
    } catch {
      setError("Failed to connect to API");
      setLoading(false);
    }
  };

  const inputStyle = {
    background: "var(--bg-elevated)",
    border: "1px solid var(--border-default)",
    color: "var(--fg-primary)",
    outline: "none",
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg-page)" }}>
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "linear-gradient(180deg, var(--blue-4), var(--blue-3))" }}>
            <Zap size={18} color="#0a0a0f" />
          </div>
          <span className="text-lg font-bold tracking-tight" style={{ color: "var(--fg-primary)" }}>
            NexusForge
          </span>
        </div>

        <div className="panel">
          <div className="panel-head">
            <span className="title">{mode === "login" ? "Sign In" : "Create Account"}</span>
          </div>
          <div className="panel-body">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--fg-muted)" }}>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-lg text-[13px]"
                  style={inputStyle}
                  placeholder="you@company.com"
                />
              </div>

              {mode === "register" && (
                <div>
                  <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--fg-muted)" }}>Username</label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg text-[13px]"
                    style={inputStyle}
                    placeholder="johndoe"
                  />
                </div>
              )}

              <div>
                <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--fg-muted)" }}>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className="w-full px-3 py-2 rounded-lg text-[13px]"
                  style={inputStyle}
                  placeholder="Min 6 characters"
                />
              </div>

              {error && (
                <div className="text-[12px] px-3 py-2 rounded-lg" style={{ background: "var(--red-1)", color: "var(--red-4)" }}>
                  {error}
                </div>
              )}

              <button type="submit" disabled={loading} className="btn primary w-full justify-center">
                {loading ? "Loading..." : mode === "login" ? "Sign In" : "Create Account"}
              </button>
            </form>

            <div className="mt-4 text-center">
              <button
                onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
                className="text-[12px] hover:underline"
                style={{ color: "var(--fg-muted)" }}
              >
                {mode === "login" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
