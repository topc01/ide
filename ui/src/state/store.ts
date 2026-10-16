import { create } from "zustand";
import type { Repo } from "../transport/envelope";

export type PanelId = "search" | "changes" | "graphite" | "tasks" | "terminal" | "notion" | "files" | "prompts" | "github" | "review" | "deps" | "config";
export interface Tab { id: string; type: "file" | "task" | "branch" | "terminal" | "page" | "airegex"; label: string; }

export interface SearchOptions { caseSensitive: boolean; wholeWord: boolean; include: string; exclude: string; context: number; }
export interface SearchLine { line: number; text: string; ranges: [number, number][]; }
export interface SearchFile { path: string; lines: SearchLine[]; }
export interface SearchResult { matches: SearchFile[]; total: number; files: number; truncated: boolean; }

interface State {
  repos: Repo[]; activePanel: PanelId; openTabs: Tab[]; activeTabId: string;
  fileTabs: Record<string, string>;          // clave (sessionId:path) -> tabId, para no reabrir el mismo archivo
  searchQuery: string; searchRegex: boolean; searchOptions: SearchOptions;
  searchResults: SearchResult | null; searchStatus: "idle" | "loading" | "done" | "error"; searchError: string | null;
  innerSidebarOpen: boolean;                 // siempre arranca expandida (no se persiste)
  toggleInnerSidebar: () => void;
  setRepos: (r: Repo[]) => void;
  setActivePanel: (p: PanelId) => void;
  openTab: (t: Tab) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  noteFileTab: (key: string, tabId: string) => void;
  setSearchQuery: (q: string) => void; setSearchRegex: (b: boolean) => void;
  setSearchOptions: (p: Partial<SearchOptions>) => void;
  setSearchStatus: (s: State["searchStatus"]) => void;
  setSearchResults: (r: SearchResult | null) => void; setSearchError: (e: string | null) => void;
}

export const useStore = create<State>((set) => ({
  repos: [], activePanel: "search", openTabs: [], activeTabId: "chat", fileTabs: {},
  searchQuery: "", searchRegex: true, searchResults: null, searchStatus: "idle", searchError: null,
  searchOptions: { caseSensitive: false, wholeWord: false, include: "", exclude: "", context: 0 },
  innerSidebarOpen: true,
  toggleInnerSidebar: () => set((s) => ({ innerSidebarOpen: !s.innerSidebarOpen })),
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
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSearchRegex: (searchRegex) => set({ searchRegex }),
  setSearchOptions: (p) => set((s) => ({ searchOptions: { ...s.searchOptions, ...p } })),
  setSearchStatus: (searchStatus) => set({ searchStatus }),
  setSearchResults: (searchResults) => set({ searchResults }),
  setSearchError: (searchError) => set({ searchError }),
}));
