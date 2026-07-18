import { create } from "zustand";
import type { StackBranch, Commit } from "../transport/graphiteChannel";
import { fetchStack, fetchBranch, restackBranch } from "../transport/graphiteChannel";
import { getWs } from "../transport/wsClient";
import { useSessions } from "./sessions";

interface GraphiteState {
  stack: StackBranch[];
  current: string | null;
  commitsByBranch: Record<string, Commit[]>;
  expandedBranches: string[];
  expandedCommits: string[];
  loading: boolean;
  error: string | null;
  restacking: string | null;
  load: (sessionId: string | null) => Promise<void>;
  toggleBranch: (sessionId: string | null, branch: string) => Promise<void>;
  toggleCommit: (hash: string) => void;
  restack: (sessionId: string | null, branch: string) => Promise<void>;
}

const stale = (sessionId: string | null) =>
  useSessions.getState().activeSessionId !== sessionId;

export const useGraphite = create<GraphiteState>((set, get) => ({
  stack: [], current: null, commitsByBranch: {}, expandedBranches: [],
  expandedCommits: [], loading: false, error: null, restacking: null,

  load: async (sessionId) => {
    set({ loading: true });
    try {
      const { stack, current } = await fetchStack(getWs(), { sessionId });
      if (stale(sessionId)) return;
      set({ stack, current, commitsByBranch: {}, expandedBranches: [],
            expandedCommits: [], loading: false, error: null });
    } catch (e: unknown) {
      if (stale(sessionId)) return;
      set({ stack: [], current: null, commitsByBranch: {}, loading: false,
            error: (e as { message?: string })?.message ?? "desconectado" });
    }
  },

  toggleBranch: async (sessionId, branch) => {
    const open = get().expandedBranches.includes(branch);
    if (open) {
      set({ expandedBranches: get().expandedBranches.filter((b) => b !== branch) });
      return;
    }
    set({ expandedBranches: [...get().expandedBranches, branch] });
    if (get().commitsByBranch[branch]) return;
    try {
      const commits = await fetchBranch(getWs(), { sessionId, branch });
      if (stale(sessionId)) return;
      set({ commitsByBranch: { ...get().commitsByBranch, [branch]: commits } });
    } catch (e: unknown) {
      if (stale(sessionId)) return;
      set({ error: (e as { message?: string })?.message ?? "desconectado" });
    }
  },

  toggleCommit: (hash) => {
    const open = get().expandedCommits.includes(hash);
    set({ expandedCommits: open
      ? get().expandedCommits.filter((h) => h !== hash)
      : [...get().expandedCommits, hash] });
  },

  restack: async (sessionId, branch) => {
    set({ restacking: branch });
    try {
      const { stack, current } = await restackBranch(getWs(), { sessionId, branch });
      if (stale(sessionId)) return;
      set({ stack, current, commitsByBranch: {}, expandedBranches: [],
            expandedCommits: [], restacking: null, error: null });
    } catch (e: unknown) {
      if (stale(sessionId)) return;
      set({ restacking: null, error: (e as { message?: string })?.message ?? "desconectado" });
    }
  },
}));
