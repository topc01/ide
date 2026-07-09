import { describe, it, expect, beforeEach } from "vitest";
import { useSessions } from "./sessions";
import type { SessionNode } from "../transport/sessions";

const node = (id: string, children: SessionNode[] = []): SessionNode =>
  ({ id, name: id, status: "idle", expanded: true, children });

describe("useSessions", () => {
  beforeEach(() => useSessions.setState({
    tree: [], repos: [], activeSessionId: null, editingId: null, modalParentId: undefined }));

  it("setData carga árbol + repos", () => {
    useSessions.getState().setData([node("a")], [{ id: "r", name: "r", branch: "main" }]);
    expect(useSessions.getState().tree).toHaveLength(1);
    expect(useSessions.getState().repos).toHaveLength(1);
  });
  it("toggleExpanded invierte expanded recursivamente", () => {
    useSessions.getState().setData([node("a", [node("b")])], []);
    useSessions.getState().toggleExpanded("b");
    const b = useSessions.getState().tree[0].children[0];
    expect(b.expanded).toBe(false);
  });
  it("toggleExpanded a profundidad 3 no muta el árbol previo", () => {
    const original = [node("a", [node("b", [node("c")])])];
    useSessions.getState().setData(original, []);
    useSessions.getState().toggleExpanded("c");
    const c = useSessions.getState().tree[0].children[0].children[0];
    expect(c.expanded).toBe(false);                       // el nodo profundo se invirtió
    // el árbol original entregado a setData no fue mutado (updates inmutables)
    expect(original[0].children[0].children[0].expanded).toBe(true);
    expect(useSessions.getState().tree).not.toBe(original);
  });
  it("openModal(null) marca crear root; closeModal cierra", () => {
    useSessions.getState().openModal(null);
    expect(useSessions.getState().modalParentId).toBe(null);
    useSessions.getState().closeModal();
    expect(useSessions.getState().modalParentId).toBe(undefined);
  });
});
