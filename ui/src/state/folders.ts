import { create } from "zustand";
import type { SessionsTree } from "../transport/folderSessions";
import { useSessions } from "./sessions";

export interface ScriptTab { terminalId: string; label: string; }
const GROUP_KEY = "ide.groupBy";
const DEV_KEY = "ide.desarrollo";             // desarrollo abierto: sobrevive a recargas/reinicios

function readDev(): { activeId: string | null; activePrUrl: string | null } {
  try {
    const v = JSON.parse(localStorage.getItem(DEV_KEY) ?? "null");
    return { activeId: v?.activeId ?? null, activePrUrl: v?.activePrUrl ?? null };
  } catch { return { activeId: null, activePrUrl: null }; }
}
function saveDev(activeId: string | null, activePrUrl: string | null) {
  try { localStorage.setItem(DEV_KEY, JSON.stringify({ activeId, activePrUrl })); } catch { /* solo memoria */ }
}

function readGroupBy(): string {
  try { return localStorage.getItem(GROUP_KEY) ?? "none"; } catch { return "none"; }
}

interface State {
  tree: SessionsTree; connected: boolean; activeId: string | null; groupBy: string;
  activePrUrl: string | null;           // card de PR (sin sesión) seleccionada: la usan los módulos
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
  tree: { sessions: [], workspaceRepos: [], scripts: {} }, connected: true, ...readDev(),
  groupBy: readGroupBy(), modal: null, uiModules: null, scriptTabs: {},
  setTree: (tree) => set({ tree, connected: true }),
  setConnected: (connected) => set({ connected }),
  setActive: (activeId) => {
    useSessions.getState().setActive(activeId); set({ activeId, activePrUrl: null }); saveDev(activeId, null);
  },
  setActivePr: (activePrUrl) => set((s) => { saveDev(s.activeId, activePrUrl); return { activePrUrl }; }),
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

// La URL enfoca una sesión: `#<id>` (p.ej. `#98`, `#manager`; el id de una sesión de ticket es su número).
// Al abrir el IDE (o cambiar el hash, p.ej. desde una notificación) se elige esa; al elegir otra, se escribe.
if (typeof window !== "undefined") {
  let pending: string | null = null;
  const apply = () => {
    const id = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    if (!id) return;
    const s = useFolders.getState();
    if (s.tree.sessions.some((x) => x.id === id)) {
      pending = null;
      if (s.activeId !== id || s.activePrUrl) s.setActive(id);
    } else {
      pending = id;                             // el árbol todavía no llega: se aplica cuando llegue
    }
  };
  window.addEventListener("hashchange", apply);
  useFolders.subscribe((s, prev) => {
    if (pending && s.tree !== prev.tree) apply();
    if (s.activeId !== prev.activeId || s.activePrUrl !== prev.activePrUrl) {
      const want = s.activeId && !s.activePrUrl ? `#${encodeURIComponent(s.activeId)}` : "";
      if (window.location.hash !== want) window.history.replaceState(null, "", want || window.location.pathname + window.location.search);
    }
  });
  apply();
}
