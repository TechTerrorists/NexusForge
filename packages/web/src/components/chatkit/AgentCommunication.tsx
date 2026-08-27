"use client";

import { useEffect, useState } from "react";
import { MessageSquare, AlertCircle, CheckCircle, HelpCircle, Eye, Send } from "lucide-react";
import { api, type AgentMessage } from "@/lib/nexus";

type Props = {
  runId: string;
};

const MESSAGE_TYPE_CONFIG: Record<string, { icon: typeof MessageSquare; color: string; label: string }> = {
  status: { icon: MessageSquare, color: "var(--blue-4)", label: "Status" },
  findings: { icon: CheckCircle, color: "var(--green-4)", label: "Findings" },
  question: { icon: HelpCircle, color: "var(--amber-4)", label: "Question" },
  answer: { icon: Send, color: "var(--purple-4)", label: "Answer" },
  review: { icon: Eye, color: "var(--cyan-4)", label: "Review" },
  error: { icon: AlertCircle, color: "var(--red-4)", label: "Error" },
};

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

export default function AgentCommunication({ runId }: Props) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runId) return;
    let active = true;
    let interval: ReturnType<typeof setInterval>;

    async function fetchMessages() {
      try {
        const data = await api<{ messages: AgentMessage[] }>(`/api/v1/runs/${runId}/messages`);
        if (active) setMessages(data.messages);
      } catch {
        // ignore polling errors
      }
    }

    fetchMessages();
    interval = setInterval(fetchMessages, 3000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [runId]);

  if (messages.length === 0) {
    return (
      <div className="panel p-4 text-center">
        <MessageSquare size={20} className="mx-auto mb-2" style={{ color: "var(--fg-muted)" }} />
        <p className="text-xs" style={{ color: "var(--fg-muted)" }}>
          Agent communication will appear here during execution.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="title">Agent Communication</span>
        <span className="badge">{messages.length} messages</span>
      </div>
      <div className="panel-body space-y-2 max-h-80 overflow-y-auto">
        {messages.map((msg) => {
          const config = MESSAGE_TYPE_CONFIG[msg.type] || MESSAGE_TYPE_CONFIG.status;
          const Icon = config.icon;
          return (
            <div key={msg.id} className="flex gap-2 items-start text-xs">
              <Icon size={12} className="mt-0.5 shrink-0" style={{ color: config.color }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium" style={{ color: config.color }}>{msg.sender}</span>
                  {msg.recipient && msg.recipient !== "coordinator" && (
                    <span style={{ color: "var(--fg-muted)" }}>→ {msg.recipient}</span>
                  )}
                  <span className="px-1 rounded" style={{ background: config.color + "15", color: config.color }}>
                    {config.label}
                  </span>
                  <span style={{ color: "var(--fg-muted)" }}>{formatTimestamp(msg.timestamp)}</span>
                </div>
                {msg.type === "findings" && typeof msg.payload.findings === "string" && (
                  <p className="mt-1 whitespace-pre-wrap" style={{ color: "var(--fg-secondary)" }}>
                    {msg.payload.findings.slice(0, 300)}
                  </p>
                )}
                {msg.type === "question" && typeof msg.payload.question === "string" && (
                  <p className="mt-1 italic" style={{ color: "var(--amber-4)" }}>
                    {msg.payload.question}
                  </p>
                )}
                {msg.type === "review" && (
                  <p className="mt-1">
                    <span style={{ color: msg.payload.approved ? "var(--green-4)" : "var(--red-4)" }}>
                      {msg.payload.approved ? "Approved" : "Rejected"}
                    </span>
                    {typeof msg.payload.feedback === "string" && <span style={{ color: "var(--fg-muted)" }}> — {msg.payload.feedback}</span>}
                  </p>
                )}
                {msg.type === "status" && typeof msg.payload.status === "string" && (
                  <p className="mt-1" style={{ color: "var(--fg-secondary)" }}>
                    {String(msg.payload.step_id)}: {msg.payload.status}
                  </p>
                )}
                {msg.artifact_refs.length > 0 && (
                  <div className="mt-1 flex gap-1 flex-wrap">
                    {msg.artifact_refs.map((ref) => (
                      <span key={ref} className="text-[10px] px-1 rounded" style={{ background: "var(--bg-elevated)", color: "var(--cyan-4)" }}>
                        {ref}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
