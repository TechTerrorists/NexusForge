"use client";

import "./globals.css";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Activity,
  UsersRound,
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
  FolderGit2,
  Menu,
} from "lucide-react";

interface NavGroup {
  label: string;
  items: { href: string; label: string; icon: React.ReactNode }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Mission control",
    items: [
      { href: "/", label: "Command Center", icon: <LayoutDashboard size={16} /> },
      { href: "/chat", label: "Tasks", icon: <MessageSquare size={16} /> },
      { href: "/runs", label: "Runs", icon: <Activity size={16} /> },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/agents", label: "Workforce", icon: <UsersRound size={16} /> },
      { href: "/workflows", label: "Automations", icon: <GitBranch size={16} /> },
      { href: "/repositories", label: "Repositories", icon: <FolderGit2 size={16} /> },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/knowledge", label: "Knowledge · Preview", icon: <Database size={16} /> },
      { href: "/marketplace", label: "Marketplace · Preview", icon: <Store size={16} /> },
      { href: "/settings", label: "Settings", icon: <Settings size={16} /> },
    ],
  },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [dark, setDark] = useState(true);
  const [authed, setAuthed] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("nf_token");
    if (pathname !== "/login" && !token) {
      router.push("/login");
      return;
    }
    setAuthed(!!token);
  }, [pathname, router]);

  const toggleTheme = () => {
    setDark((d) => {
      const next = !d;
      document.documentElement.classList.toggle("dark", next);
      return next;
    });
  };

  if (pathname === "/login") {
    return (
      <html lang="en" className="dark">
        <body>
          <div className="min-h-screen bg-gray-50 dark:bg-[#0a0a0f] text-gray-900 dark:text-gray-100">
            {children}
          </div>
        </body>
      </html>
    );
  }

  if (!authed) {
    return (
      <html lang="en" className="dark">
        <body>
          <div className="min-h-screen bg-gray-50 dark:bg-[#0a0a0f]" />
        </body>
      </html>
    );
  }

  return (
    <html lang="en" className="dark">
      <body>
        <div className="flex h-screen bg-gray-50 dark:bg-[#0a0a0f] text-gray-900 dark:text-gray-100">
          {/* Sidebar */}
          {navOpen && <button aria-label="Close navigation overlay" className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setNavOpen(false)} />}
          <aside className={`mission-sidebar ${navOpen ? "open" : ""}`}>
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
                          <span>{item.label.replace(" · Preview", "")}</span>
                          {item.label.includes("Preview") && <span className="ml-auto text-[8px] uppercase tracking-wider" style={{ color: "var(--amber-4)" }}>Preview</span>}
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
            <header className="h-14 shrink-0 flex items-center gap-3 px-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-[#0f0f17]">
              <button aria-label="Open navigation" className="p-2 lg:hidden" onClick={() => setNavOpen(true)}><Menu size={18} /></button>
              <div className="flex-1 max-w-md">
                <div className="relative">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search workflows, agents, runs..."
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter" || !search.trim()) return;
                      const match = NAV_GROUPS.flatMap((group) => group.items).find((item) => item.label.toLowerCase().includes(search.toLowerCase()));
                      if (match) { router.push(match.href); setSearch(""); }
                    }}
                    className="w-full pl-8 pr-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-md text-xs bg-gray-50 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:outline-none focus:ring-1 focus:ring-brand-500 focus:border-brand-500"
                  />
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button className="relative p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-white/5 transition-colors" title="No unread notifications" aria-label="Notifications">
                  <Bell size={16} className="text-gray-500 dark:text-gray-400" />
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
