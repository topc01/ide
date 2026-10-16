import { create } from "zustand";
import type { SessionsTree } from "../transport/folderSessions";
import { useSessions } from "./sessions";

export interface ScriptTab { terminalId: string; label: string; }
const GROUP_KEY = "ide.groupBy";

function readGroupBy(): string {
  try { return localStorage.getItem(GROUP_KEY) ?? "none"; } catch { return "none"; }
}

interface State {
  tree: SessionsTree; connected: boolean; activeId: string | null; groupBy: string;
  activePrUrl: string | null;           // card de PR (sin sesión) seleccionada: la usa el módulo GitHub
  modal: null | "session" | "review"; uiModules: string[] | null;
  scriptTabs: Record<string, ScriptTab[]>;
  setTree: (t: SessionsTree) => void; setConnected: (c: boolean) => void;
  setActive: (id: string) => void; setGroupBy: (id: string) => void;
  setActivePr: (url: string | null) => void;
  openModal: (m: "session" | "review") => void; closeModal: () => void;
  setUiModules: (m: string[]) => void;
  addScriptTab: (sid: string, tab: ScriptTab) => void;
  closeScriptTab: (sid: string, terminalId: string) => void;
}

export const useFolders = create<State>((set) => ({
  tree: { sessions: [], workspaceRepos: [], scripts: {} }, connected: true, activeId: null, activePrUrl: null,
  groupBy: readGroupBy(), modal: null, uiModules: null, scriptTabs: {},
  setTree: (tree) => set({ tree, connected: true }),
  setConnected: (connected) => set({ connected }),
  setActive: (activeId) => { useSessions.getState().setActive(activeId); set({ activeId, activePrUrl: null }); },
  setActivePr: (activePrUrl) => set({ activePrUrl }),
  setGroupBy: (groupBy) => {
    try { localStorage.setItem(GROUP_KEY, groupBy); } catch { /* storage bloqueado: solo memoria */ }
    set({ groupBy });
  },
  openModal: (modal) => set({ modal }), closeModal: () => set({ modal: null }),
  setUiModules: (uiModules) => set({ uiModules }),
  addScriptTab: (sid, tab) => set((s) => {
    const tabs = s.scriptTabs[sid] ?? [];
    if (tabs.some((t) => t.terminalId === tab.terminalId)) return s;
    return { scriptTabs: { ...s.scriptTabs, [sid]: [...tabs, tab] } };
  }),
  closeScriptTab: (sid, terminalId) => set((s) => ({
    scriptTabs: { ...s.scriptTabs,
      [sid]: (s.scriptTabs[sid] ?? []).filter((t) => t.terminalId !== terminalId) } })),
}));
