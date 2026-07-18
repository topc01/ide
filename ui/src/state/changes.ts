import { create } from "zustand";
import type { RepoStatus } from "../transport/changesChannel";
import { fetchChanges } from "../transport/changesChannel";
import { getWs } from "../transport/wsClient";
import { useSessions } from "./sessions";

interface ChangesState {
  status: RepoStatus | null;
  loading: boolean;
  error: string | null;
  load: (sessionId: string | null) => Promise<void>;
}

export const useChanges = create<ChangesState>((set) => ({
  status: null, loading: false, error: null,
  load: async (sessionId) => {
    set({ loading: true });
    try {
      const status = await fetchChanges(getWs(), { sessionId });
      // Si cambiamos de sesión mientras el fetch estaba en vuelo, descartamos
      // el resultado: nunca mostrar datos de otra sesión como si fueran los
      // de la sesión activa (evita "stale cross-session data shown as live").
      if (useSessions.getState().activeSessionId !== sessionId) return;
      set({ status, loading: false, error: null });
    } catch (e: unknown) {
      if (useSessions.getState().activeSessionId !== sessionId) return;
      const message = (e as { message?: string })?.message ?? "desconectado";
      set({ status: null, loading: false, error: message });
    }
  },
}));
