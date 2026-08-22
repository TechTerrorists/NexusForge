import { create } from "zustand";

interface Workflow {
  id: string;
  name: string;
  status: "draft" | "active" | "archived";
  updatedAt: string;
}

interface Agent {
  id: string;
  name: string;
  model: string;
  status: "running" | "idle";
  tools: string[];
  runCount: number;
}

interface User {
  id: string;
  email: string;
  name: string;
}

interface AppState {
  workflows: Workflow[];
  selectedWorkflowId: string | null;
  setWorkflows: (workflows: Workflow[]) => void;
  selectWorkflow: (id: string | null) => void;

  agents: Agent[];
  setAgents: (agents: Agent[]) => void;

  theme: "light" | "dark";
  toggleTheme: () => void;

  auth: {
    token: string | null;
    user: User | null;
    login: (token: string, user: User) => void;
    logout: () => void;
  };
}

export const useAppStore = create<AppState>((set) => ({
  workflows: [],
  selectedWorkflowId: null,
  setWorkflows: (workflows) => set({ workflows }),
  selectWorkflow: (id) => set({ selectedWorkflowId: id }),

  agents: [],
  setAgents: (agents) => set({ agents }),

  theme: "light",
  toggleTheme: () =>
    set((state) => {
      const next = state.theme === "light" ? "dark" : "light";
      document.documentElement.classList.toggle("dark", next === "dark");
      return { theme: next };
    }),

  auth: {
    token: null,
    user: null,
    login: (token, user) => set({ auth: { token, user, login: () => {}, logout: () => {} } }),
    logout: () =>
      set({ auth: { token: null, user: null, login: () => {}, logout: () => {} } }),
  },
}));
