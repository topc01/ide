// ui/src/state/sidebarConfig.ts
import { create } from "zustand";

/** Cómo se agrupa cada sección de la sidebar (Revisiones, Mis PRs). Se recuerda por navegador.
 *  `focus`: sección cuyo ⚙ abrió el módulo Configuración (se resalta ahí). */
export type GroupBy = "status" | "repo" | "stack" | "author" | "none";

const KEY = (id: string) => `ide.groupBy.${id}`;
function read(id: string): GroupBy {
  try { return (localStorage.getItem(KEY(id)) as GroupBy) || "status"; } catch { return "status"; }
}

interface State {
  groupBy: Record<string, GroupBy>;
  focus: string | null;
  setGroupBy: (id: string, g: GroupBy) => void;
  setFocus: (id: string | null) => void;
}

export const useSidebarConfig = create<State>((set) => ({
  groupBy: { reviews: read("reviews"), myprs: read("myprs") },
  focus: null,
  setGroupBy: (id, g) => {
    try { localStorage.setItem(KEY(id), g); } catch { /* solo memoria */ }
    set((s) => ({ groupBy: { ...s.groupBy, [id]: g } }));
  },
  setFocus: (focus) => set({ focus }),
}));
