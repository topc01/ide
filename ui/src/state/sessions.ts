import { create } from "zustand";
import type { SessionNode } from "../transport/sessions";
import type { Repo } from "../transport/envelope";

function mapTree(nodes: SessionNode[], id: string, fn: (n: SessionNode) => SessionNode): SessionNode[] {
  return nodes.map((n) =>
    n.id === id ? fn(n) : { ...n, children: mapTree(n.children, id, fn) });
}

interface State {
  tree: SessionNode[]; repos: Repo[];
  activeSessionId: string | null; editingId: string | null;
  modalParentId: string | null | undefined;   // undefined = cerrado
  setData: (sessions: SessionNode[], repos: Repo[]) => void;
  setActive: (id: string) => void;
  toggleExpanded: (id: string) => void;
  startRename: (id: string) => void;
  stopRename: () => void;
  applyRename: (id: string, name: string) => void;
  openModal: (parentId: string | null) => void;
  closeModal: () => void;
}

export const useSessions = create<State>((set) => ({
  tree: [], repos: [], activeSessionId: null, editingId: null, modalParentId: undefined,
  setData: (tree, repos) => set({ tree, repos }),
  setActive: (activeSessionId) => set({ activeSessionId }),
  toggleExpanded: (id) => set((s) => ({
    tree: mapTree(s.tree, id, (n) => ({ ...n, expanded: !n.expanded })) })),
  startRename: (editingId) => set({ editingId }),
  stopRename: () => set({ editingId: null }),
  applyRename: (id, name) => set((s) => ({
    tree: mapTree(s.tree, id, (n) => ({ ...n, name })) })),
  openModal: (modalParentId) => set({ modalParentId }),
  closeModal: () => set({ modalParentId: undefined }),
}));
