"use client";

import { useState, useRef, useEffect } from "react";
import {
  Send,
  PanelLeftClose,
  PanelLeft,
  Bot,
  User,
  Loader2,
  Trash2,
  Copy,
  Check,
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  status?: "sending" | "streaming" | "done" | "error";
}

const DEMO_MESSAGES: Message[] = [
  {
    id: "m1",
    role: "user",
    content: "Can you analyze the sales data from last quarter?",
    timestamp: new Date(Date.now() - 300000),
    status: "done",
  },
  {
    id: "m2",
    role: "assistant",
    content:
      "I'll analyze the Q4 sales data for you. Let me query the database and prepare a summary.\n\n**Key Findings:**\n- Total revenue: $2.4M (12% QoQ)\n- Top product: Enterprise Plan (42% of revenue)\n- Best region: North America (38% of sales)\n- New customer acquisition: 847 accounts\n\nWould you like me to drill down into any specific area?",
    timestamp: new Date(Date.now() - 295000),
    status: "done",
  },
  {
    id: "m3",
    role: "user",
    content: "Break down the Enterprise Plan performance by vertical.",
    timestamp: new Date(Date.now() - 280000),
    status: "done",
  },
  {
    id: "m4",
    role: "assistant",
    content:
      "Here's the Enterprise Plan breakdown by vertical:\n\n- FinTech: $420K (+18%)\n- Healthcare: $312K (+24%)\n- SaaS: $285K (+9%)\n- Manufacturing: $198K (+15%)\n\nFinTech remains the strongest vertical. Healthcare shows the highest growth rate, driven by the new HIPAA-compliant features launched in November.",
    timestamp: new Date(Date.now() - 275000),
    status: "done",
  },
];

const STREAM_RESPONSE =
  "I'm processing your request. This is a demo response from the NexusForge chat interface. In production, this would stream tokens from the configured LLM provider via Server-Sent Events.";

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>(DEMO_MESSAGES);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = () => {
    if (!input.trim() || isStreaming) return;

    const userMessage: Message = {
      id: `m${Date.now()}`,
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
      status: "done",
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsStreaming(true);

    const assistantId = `m${Date.now() + 1}`;
    const assistantMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      status: "streaming",
    };

    setMessages((prev) => [...prev, assistantMessage]);

    let currentContent = "";
    const chars = STREAM_RESPONSE.split("");
    let i = 0;

    const streamInterval = setInterval(() => {
      if (i < chars.length) {
        const chunk = chars.slice(i, i + 3).join("");
        currentContent += chunk;
        i += 3;

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: currentContent } : m
          )
        );
      } else {
        clearInterval(streamInterval);
        setIsStreaming(false);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, status: "done" } : m
          )
        );
      }
    }, 20);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const copyMessage = (id: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const clearChat = () => {
    setMessages([]);
  };

  return (
    <div className="flex h-full">
      {sidebarOpen && (
        <div
          className="w-56 shrink-0 flex flex-col"
          style={{
            borderRight: "1px solid var(--border-subtle)",
            background: "var(--bg-canvas)",
          }}
        >
          <div
            className="flex items-center justify-between px-3 py-2.5"
            style={{ borderBottom: "1px solid var(--border-subtle)" }}
          >
            <h3 className="text-[13px] font-medium">Sessions</h3>
            <button
              onClick={() => setSidebarOpen(false)}
              className="p-1 rounded hover:bg-white/5"
            >
              <PanelLeftClose size={14} style={{ color: "var(--fg-muted)" }} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            <div
              className="px-2.5 py-1.5 rounded text-[13px] font-medium cursor-pointer"
              style={{
                background: "rgba(110,161,240,0.1)",
                color: "var(--blue-4)",
                borderLeft: "2px solid var(--blue-4)",
              }}
            >
              Sales Data Analysis
            </div>
            {["Code Review Session", "Support Ticket Triage", "Research: Market Trends"].map(
              (name) => (
                <div
                  key={name}
                  className="px-2.5 py-1.5 text-[13px] rounded cursor-pointer hover:bg-white/5"
                  style={{ color: "var(--fg-muted)" }}
                >
                  {name}
                </div>
              )
            )}
          </div>
          <div className="p-2" style={{ borderTop: "1px solid var(--border-subtle)" }}>
            <button className="btn primary w-full justify-center text-[13px]">
              + New Chat
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <div
          className="flex items-center justify-between px-4 py-2.5 shrink-0"
          style={{ borderBottom: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-center gap-2">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-1 rounded hover:bg-white/5"
              >
                <PanelLeft size={16} style={{ color: "var(--fg-muted)" }} />
              </button>
            )}
            <h3 className="text-[13px] font-medium">Sales Data Analysis</h3>
          </div>
          <button
            onClick={clearChat}
            className="p-1 rounded hover:bg-white/5"
            style={{ color: "var(--fg-muted)" }}
            title="Clear chat"
          >
            <Trash2 size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${
                message.role === "user" ? "justify-end" : ""
              }`}
            >
              {message.role === "assistant" && (
                <div
                  className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center"
                  style={{
                    background: "var(--blue-1)",
                    border: "1px solid var(--blue-2)",
                  }}
                >
                  <Bot size={14} style={{ color: "var(--blue-4)" }} />
                </div>
              )}

              <div
                className="max-w-[70%] rounded-lg p-3 text-[13px] leading-relaxed"
                style={{
                  background:
                    message.role === "user" ? "var(--blue-3)" : "var(--bg-elevated)",
                  color:
                    message.role === "user" ? "#0a0a0f" : "var(--fg-secondary)",
                  border:
                    message.role === "assistant"
                      ? "1px solid var(--border-subtle)"
                      : "none",
                }}
              >
                <div className="whitespace-pre-wrap">
                  {message.content}
                  {message.status === "streaming" && (
                    <span
                      className="inline-block w-1.5 h-4 animate-pulse ml-0.5 align-text-bottom"
                      style={{ background: "var(--blue-4)" }}
                    />
                  )}
                </div>
                <div
                  className="flex items-center gap-2 mt-2 text-[11px]"
                  style={{
                    color:
                      message.role === "user"
                        ? "rgba(10,10,15,0.5)"
                        : "var(--fg-muted)",
                  }}
                >
                  <span suppressHydrationWarning>
                    {message.timestamp.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  {message.role === "assistant" && message.status === "done" && (
                    <button
                      onClick={() => copyMessage(message.id, message.content)}
                      className="hover:opacity-100 opacity-50 transition-opacity"
                    >
                      {copiedId === message.id ? (
                        <Check size={12} />
                      ) : (
                        <Copy size={12} />
                      )}
                    </button>
                  )}
                </div>
              </div>

              {message.role === "user" && (
                <div
                  className="shrink-0 w-7 h-7 rounded-lg flex items-center justify-center"
                  style={{ background: "var(--bg-overlay)" }}
                >
                  <User size={14} style={{ color: "var(--fg-muted)" }} />
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div
          className="p-4 shrink-0"
          style={{ borderTop: "1px solid var(--border-subtle)" }}
        >
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message... (Shift+Enter for newline)"
              rows={1}
              className="flex-1 px-3 py-2 rounded-lg text-[13px] resize-none focus:outline-none focus:ring-1 max-h-32"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-default)",
                color: "var(--fg-primary)",
                minHeight: "40px",
                ["--tw-ring-color" as string]: "var(--border-focus)",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height =
                  Math.min(target.scrollHeight, 128) + "px";
              }}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || isStreaming}
              className="p-2 rounded-lg hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
              style={{
                background: "var(--blue-3)",
                color: "#0a0a0f",
              }}
            >
              {isStreaming ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
