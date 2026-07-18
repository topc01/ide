import { create } from "zustand";
import type { NotionRef } from "../transport/notionChannel";
import { checkHealth, fetchPages, addPage, removePage } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";

interface NotionState {
  connected: boolean; pages: NotionRef[]; loading: boolean; error: string | null;
  load: () => Promise<void>;
  add: (url: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}
const msg = (e: unknown) => (e as { message?: string })?.message ?? "desconectado";

export const useNotion = create<NotionState>((set, get) => ({
  connected: false, pages: [], loading: false, error: null,
  load: async () => {
    set({ loading: true });
    try {
      const connected = await checkHealth(getWs());
      const pages = connected ? await fetchPages(getWs()) : [];
      set({ connected, pages, loading: false, error: null });
    } catch (e) { set({ loading: false, error: msg(e) }); }
  },
  add: async (url) => {
    try { await addPage(getWs(), url); set({ pages: await fetchPages(getWs()), error: null }); }
    catch (e) { set({ error: msg(e) }); }
  },
  remove: async (id) => {
    try { await removePage(getWs(), id); set({ pages: await fetchPages(getWs()) }); }
    catch (e) { set({ error: msg(e) }); }
  },
}));
