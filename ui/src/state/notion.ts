import { create } from "zustand";
import type { NotionRef } from "../transport/notionChannel";
import { checkHealth, fetchPages, addPage, removePage, connect as connectApi, disconnect as disconnectApi } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";

interface NotionState {
  connected: boolean; pages: NotionRef[]; loading: boolean; error: string | null;
  load: () => Promise<void>;
  add: (url: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  connect: (token: string) => Promise<void>;
  disconnect: () => Promise<void>;
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
  connect: async (token: string) => {
    try {
      const ok = await connectApi(getWs(), token);
      if (ok) { await get().load(); }
      else { set({ connected: false, error: "token inválido" }); }
    } catch (e) { set({ error: msg(e) }); }
  },
  disconnect: async () => {
    try { await disconnectApi(getWs()); set({ connected: false, pages: [], error: null }); }
    catch (e) { set({ error: msg(e) }); }
  },
}));
