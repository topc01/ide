import { describe, it, expect } from "vitest";
import { fetchTree, createSession, fetchBranches } from "./sessions";

function fakeWs(response: any) {
  return { request: (_c: string, _p: any) => Promise.resolve(response) } as any;
}

describe("transport/sessions", () => {
  it("fetchTree devuelve sessions + repos", async () => {
    const ws = fakeWs({ sessions: [{ id: "s1", name: "A", status: "idle", children: [] }], repos: [] });
    const out = await fetchTree(ws);
    expect(out.sessions[0].name).toBe("A");
  });
  it("createSession pasa el payload por el canal", async () => {
    const ws = fakeWs({ session: { id: "s2", name: "B", status: "idle", children: [] } });
    const out = await createSession(ws, { name: "B", kind: "coordinator" });
    expect(out.session.id).toBe("s2");
  });
  it("fetchBranches devuelve branches", async () => {
    const ws = fakeWs({ branches: [{ name: "main", occupied: true }] });
    const out = await fetchBranches(ws, "repoA");
    expect(out[0].occupied).toBe(true);
  });
});
