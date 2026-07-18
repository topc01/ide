import { create } from "zustand";
import type { RepoStatus } from "../transport/changesChannel";
import { fetchChanges } from "../transport/changesChannel";
import { getWs } from "../transport/wsClient";

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
      set({ status, loading: false, error: null });
    } catch (e: unknown) {
      const message = (e as { message?: string })?.message ?? "desconectado";
      set({ status: null, loading: false, error: message });
    }
  },
}));
