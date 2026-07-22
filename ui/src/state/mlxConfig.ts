import { create } from "zustand";

export interface MlxConfig { enabled: boolean; model: string; routerPrompt: string; defaultPrompt: string; }

interface MlxConfigState extends MlxConfig {
  loaded: boolean; error: string | null;
  setConfig: (c: MlxConfig) => void;
  update: (partial: Partial<MlxConfig>) => void;
  setError: (e: string | null) => void;
}

export const useMlxConfig = create<MlxConfigState>((set) => ({
  enabled: false, model: "", routerPrompt: "", defaultPrompt: "", loaded: false, error: null,
  setConfig: (c) => set({ ...c, loaded: true, error: null }),
  update: (partial) => set(partial),
  setError: (error) => set({ error }),
}));
