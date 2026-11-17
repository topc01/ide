// ui/src/modules/later/focus.ts
/** El bloqueante a marcar en el módulo Bloqueantes (click en uno desde la card): el panel lo trae a la vista. */
import { create } from "zustand";

export const useLaterFocus = create<{ id: string | null; set: (id: string | null) => void }>((set) => ({
  id: null, set: (id) => set({ id }),
}));

/** Cuántos bloqueantes están en curso: sin los de desarrollos pausados ni archivados (van en sus secciones). */
export const activeBlockers = (s: { tree: { later?: { key: string; archived?: boolean }[]; devStates?: Record<string, { block?: string | null }> } }) =>
  (s.tree.later ?? []).filter((it) => !it.archived && s.tree.devStates?.[it.key]?.block !== "paused").length;
