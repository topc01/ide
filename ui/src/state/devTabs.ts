// ui/src/state/devTabs.ts
import { create } from "zustand";

/** Una tab del panel principal. Cada desarrollo tiene su propia fila de tabs. */
export interface DevTab {
  id: string;                                   // único dentro del desarrollo
  kind: "claude" | "doc" | "summary" | "script" | "run" | "file" | "diff";
  label: string;
  sid?: string;                                 // claude / doc
  url?: string;                                 // summary (PR)
  terminalId?: string;                          // script
  place?: string; repo?: string;                // run / file: worktree (`place` = sesión o `wt-<repo>-<n>`)
  name?: string;                                // run: script
  path?: string;                                // file: relativa al worktree; diff: del repo
  oldPath?: string | null;                      // diff: si se renombró
}
interface DevTabsState {
  byDev: Record<string, { tabs: DevTab[]; active: string | null }>;
  open: (dev: string, tab: DevTab, focus?: boolean) => void;
  close: (dev: string, id: string) => void;
  focus: (dev: string, id: string) => void;
}

const KEY = "ide.devTabs";
function load(): DevTabsState["byDev"] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "{}") as DevTabsState["byDev"];
    // las terminales de scripts mueren con el server: no se recuerdan
    for (const d of Object.values(raw)) {
      d.tabs = d.tabs.filter((t) => t.kind !== "script");
      if (!d.tabs.some((t) => t.id === d.active)) d.active = d.tabs[0]?.id ?? null;
    }
    return raw;
  } catch { return {}; }
}
function save(byDev: DevTabsState["byDev"]) {
  try { localStorage.setItem(KEY, JSON.stringify(byDev)); } catch { /* solo memoria */ }
}

export const useDevTabs = create<DevTabsState>((set) => ({
  byDev: load(),
  open: (dev, tab, focus = true) => set((s) => {
    const cur = s.byDev[dev] ?? { tabs: [], active: null };
    const tabs = cur.tabs.some((t) => t.id === tab.id) ? cur.tabs : [...cur.tabs, tab];
    const byDev = { ...s.byDev, [dev]: { tabs, active: focus || !cur.active ? tab.id : cur.active } };
    save(byDev);
    return { byDev };
  }),
  close: (dev, id) => set((s) => {
    const cur = s.byDev[dev];
    if (!cur) return s;
    const i = cur.tabs.findIndex((t) => t.id === id);
    const tabs = cur.tabs.filter((t) => t.id !== id);
    const active = cur.active === id ? (tabs[Math.max(0, i - 1)]?.id ?? null) : cur.active;
    const byDev = { ...s.byDev, [dev]: { tabs, active } };
    save(byDev);
    return { byDev };
  }),
  focus: (dev, id) => set((s) => {
    const cur = s.byDev[dev];
    if (!cur) return s;
    const byDev = { ...s.byDev, [dev]: { ...cur, active: id } };
    save(byDev);
    return { byDev };
  }),
}));

export const claudeTab = (sid: string): DevTab => ({ id: `claude:${sid}`, kind: "claude", label: "claude", sid });
export const docTab = (sid: string, name: string): DevTab => ({ id: `doc:${sid}`, kind: "doc", label: name, sid });
export const summaryTab = (url: string, label: string): DevTab => ({ id: `summary:${url}`, kind: "summary", label, url });
export const scriptTab = (terminalId: string, label: string): DevTab =>
  ({ id: `script:${terminalId}`, kind: "script", label, terminalId });
export const runTab = (place: string, repo: string, name: string, label: string): DevTab =>
  ({ id: `run:${place}/${repo}/${name}`, kind: "run", label, place, repo, name });
export const fileTab = (place: string, repo: string, path: string): DevTab =>
  ({ id: `file:${place}/${repo}/${path}`, kind: "file", label: path.split("/").pop() || path, place, repo, path });
export const diffTab = (url: string, path: string, oldPath: string | null): DevTab =>
  ({ id: `diff:${url}:${path}`, kind: "diff", label: `Δ ${path.split("/").pop() || path}`, url, path, oldPath });
