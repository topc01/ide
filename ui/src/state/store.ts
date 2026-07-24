import { create } from "zustand";
import type { Repo } from "../transport/envelope";

export type PanelId = "search" | "changes" | "graphite" | "tasks" | "terminal" | "notion" | "files";
export interface Tab { id: string; type: "file" | "task" | "branch" | "terminal" | "page"; label: string; }

interface State {
  repos: Repo[]; activePanel: PanelId; openTabs: Tab[]; activeTabId: string;
  fileTabs: Record<string, string>;          // clave (sessionId:path) -> tabId, para no reabrir el mismo archivo
  setRepos: (r: Repo[]) => void;
  setActivePanel: (p: PanelId) => void;
  openTab: (t: Tab) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  noteFileTab: (key: string, tabId: string) => void;
}

export const useStore = create<State>((set) => ({
  repos: [], activePanel: "search", openTabs: [], activeTabId: "chat", fileTabs: {},
  setRepos: (repos) => set({ repos }),
  setActivePanel: (activePanel) => set({ activePanel }),
  openTab: (t) => set((s) => ({
    openTabs: s.openTabs.some((x) => x.id === t.id) ? s.openTabs : [...s.openTabs, t],
    activeTabId: t.id,
  })),
  closeTab: (id) => set((s) => {
    const tabs = s.openTabs.filter((t) => t.id !== id);
    const active = s.activeTabId === id ? (tabs.at(-1)?.id ?? "chat") : s.activeTabId;
    // limpiar el mapa archivo->tab para que reabrir vuelva a spawnear
    const fileTabs = Object.fromEntries(Object.entries(s.fileTabs).filter(([, v]) => v !== id));
    return { openTabs: tabs, activeTabId: active, fileTabs };
  }),
  setActiveTab: (id) => set({ activeTabId: id }),
  noteFileTab: (key, tabId) => set((s) => ({ fileTabs: { ...s.fileTabs, [key]: tabId } })),
}));
