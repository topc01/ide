// ui/src/modules/later/focus.ts
/** El bloqueante a marcar en el módulo Bloqueantes (click en uno desde la card): el panel lo trae a la vista. */
import { create } from "zustand";

export const useLaterFocus = create<{ id: string | null; set: (id: string | null) => void }>((set) => ({
  id: null, set: (id) => set({ id }),
}));
