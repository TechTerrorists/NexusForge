"use client";

import "./globals.css";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LayoutDashboard,
  Activity,
  Bot,
  GitBranch,
  Database,
  Store,
  Settings,
  MessageSquare,
  Moon,
  Sun,
  Search,
  Bell,
  ChevronDown,
  Zap,
} from "lucide-react";

interface NavGroup {
  label: string;
  items: { href: string; label: string; icon: React.ReactNode }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Observe",
    items: [
      { href: "/", label: "Overview", icon: <LayoutDashboard size={16} /> },
      { href: "/runs", label: "Live Runs", icon: <Activity size={16} /> },
      { href: "/agents", label: "Agents", icon: <Bot size={16} /> },
    ],
  },
  {
    label: "Build",
    items: [
      { href: "/workflows", label: "Workflows", icon: <GitBranch size={16} /> },
      { href: "/knowledge", label: "Knowledge", icon: <Database size={16} /> },
      { href: "/marketplace", label: "Marketplace", icon: <Store size={16} /> },
    ],
  },
  {
    label: "Operate",
    items: [
      { href: "/chat", label: "Chat", icon: <MessageSquare size={16} /> },
      { href: "/settings", label: "Settings", icon: <Settings size={16} /> },
    ],
  },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [dark, setDark] = useState(true);

  const toggleTheme = () => {
    setDark((d) => {
      const next = !d;
      document.documentElement.classList.toggle("dark", next);
      return next;
    });
  };

  return (
    <html lang="en" className="dark">
      <body>
        <div className="flex h-screen bg-gray-50 dark:bg-[#0a0a0f] text-gray-900 dark:text-gray-100">
          {/* Sidebar */}
          <aside className="w-56 shrink-0 border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-[#0f0f17] flex flex-col">
            {/* Brand */}
            <div className="h-12 flex items-center gap-2 px-4 border-b border-gray-200 dark:border-gray-800">
              <div className="w-6 h-6 rounded bg-brand-600 flex items-center justify-center">
                <Zap size={14} className="text-white" />
              </div>
              <span className="text-sm font-bold tracking-tight">NexusForge</span>
            </div>

            {/* Nav Groups */}
            <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
              {NAV_GROUPS.map((group) => (
                <div key={group.label}>
                  <div className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">
                    {group.label}
                  </div>
                  <div className="space-y-0.5">
                    {group.items.map((item) => {
                      const active = pathname === item.href;
                      return (
                        <a
                          key={item.href}
                          href={item.href}
                          className={`flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                            active
                              ? "bg-brand-50 text-brand-600 dark:bg-brand-600/10 dark:text-brand-400 font-medium"
                              : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/5"
                          }`}
                        >
                          <span className={active ? "text-brand-500 dark:text-brand-400" : "text-gray-400 dark:text-gray-500"}>
                            {item.icon}
                          </span>
                          {item.label}
                        </a>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>

            {/* Footer */}
            <div className="p-3 border-t border-gray-200 dark:border-gray-800">
              <div className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-white/5 cursor-pointer transition-colors">
                <div className="w-6 h-6 rounded-full bg-brand-600 flex items-center justify-center text-[10px] font-bold text-white">
                  T
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">TechTerrorists</div>
                  <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">admin</div>
                </div>
                <ChevronDown size={12} className="text-gray-400" />
              </div>
            </div>
          </aside>

          {/* Main area */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Topbar */}
            <header className="h-12 shrink-0 flex items-center gap-3 px-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-[#0f0f17]">
              <div className="flex-1 max-w-md">
                <div className="relative">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search workflows, agents, runs..."
                    className="w-full pl-8 pr-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-md text-xs bg-gray-50 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                  />
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button className="relative p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-white/5 transition-colors">
                  <Bell size={16} className="text-gray-500 dark:text-gray-400" />
                  <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-red-500 rounded-full" />
                </button>
                <button
                  onClick={toggleTheme}
                  className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
                  title="Toggle theme"
                >
                  {dark ? (
                    <Sun size={16} className="text-gray-500 dark:text-gray-400" />
                  ) : (
                    <Moon size={16} className="text-gray-500" />
                  )}
                </button>
              </div>
            </header>

            {/* Content */}
            <main className="flex-1 overflow-auto">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
