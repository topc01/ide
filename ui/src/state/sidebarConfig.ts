// ui/src/state/sidebarConfig.ts
import { create } from "zustand";

/** Cómo se agrupa cada sección de la sidebar (Revisiones, Mis PRs). Se recuerda por navegador.
 *  `focus`: sección cuyo ⚙ abrió el módulo Configuración (se resalta ahí). */
export type GroupBy = "status" | "devstate" | "repo" | "stack" | "author" | "none";
/** Color de las cards: el de la PR (review) o el del estado del desarrollo. Solo se elige cuando la
 *  agrupación no es una de esas dos dimensiones (si lo es, manda la agrupación). */
export type ColorBy = "pr" | "dev";
const CKEY = (id: string) => `ide.colorBy.${id}`;
function readColor(id: string): ColorBy {
  try { return (localStorage.getItem(CKEY(id)) as ColorBy) || "pr"; } catch { return "pr"; }
}
export const effectiveColor = (by: GroupBy, color: ColorBy): ColorBy =>
  by === "status" ? "pr" : by === "devstate" ? "dev" : color;

const KEY = (id: string) => `ide.groupBy.${id}`;
function read(id: string): GroupBy {
  try { return (localStorage.getItem(KEY(id)) as GroupBy) || "status"; } catch { return "status"; }
}

interface State {
  groupBy: Record<string, GroupBy>;
  focus: string | null;
  colorBy: Record<string, ColorBy>;
  setGroupBy: (id: string, g: GroupBy) => void;
  setColorBy: (id: string, c: ColorBy) => void;
  setFocus: (id: string | null) => void;
}

export const useSidebarConfig = create<State>((set) => ({
  groupBy: { reviews: read("reviews"), mine: read("mine") },
  focus: null,
  colorBy: { mine: readColor("mine") },
  setColorBy: (id, c) => {
    try { localStorage.setItem(CKEY(id), c); } catch { /* solo memoria */ }
    set((s) => ({ colorBy: { ...s.colorBy, [id]: c } }));
  },
  setGroupBy: (id, g) => {
    try { localStorage.setItem(KEY(id), g); } catch { /* solo memoria */ }
    set((s) => ({ groupBy: { ...s.groupBy, [id]: g } }));
  },
  setFocus: (focus) => set({ focus }),
}));
