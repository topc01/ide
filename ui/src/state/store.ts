import { create } from "zustand";
import type { Repo } from "../transport/envelope";

export type PanelId = "search" | "changes" | "graphite" | "tasks" | "terminal" | "notion" | "files";
export interface Tab { id: string; type: "file" | "task" | "branch" | "terminal" | "page"; label: string; }

interface State {
  repos: Repo[]; activePanel: PanelId; openTabs: Tab[]; activeTabId: string;
  setRepos: (r: Repo[]) => void;
  setActivePanel: (p: PanelId) => void;
  openTab: (t: Tab) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
}

export const useStore = create<State>((set) => ({
  repos: [], activePanel: "search", openTabs: [], activeTabId: "chat",
  setRepos: (repos) => set({ repos }),
  setActivePanel: (activePanel) => set({ activePanel }),
  openTab: (t) => set((s) => ({
    openTabs: s.openTabs.some((x) => x.id === t.id) ? s.openTabs : [...s.openTabs, t],
    activeTabId: t.id,
  })),
  closeTab: (id) => set((s) => {
    const tabs = s.openTabs.filter((t) => t.id !== id);
    const active = s.activeTabId === id ? (tabs.at(-1)?.id ?? "chat") : s.activeTabId;
    return { openTabs: tabs, activeTabId: active };
  }),
  setActiveTab: (id) => set({ activeTabId: id }),
}));
