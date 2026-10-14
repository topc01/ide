import { describe, it, expect, vi } from "vitest";
import { fetchSessions, newSession, runScript, onSessionsChanged, rmSession } from "./folderSessions";

function fakeWs() {
  const listeners: Record<string, (p: any) => void> = {};
  return {
    request: vi.fn().mockResolvedValue({ ok: true }),
    on: vi.fn((c: string, cb: any) => { listeners[c] = cb; }),
    off: vi.fn((c: string) => { delete listeners[c]; }),
    emit: (c: string, p: any) => listeners[c]?.(p),
  };
}

describe("folderSessions transport", () => {
  it("usa los canales sessions.*", async () => {
    const ws = fakeWs();
    await fetchSessions(ws as any);
    await newSession(ws as any, { id: "FIN-1", template: "ticket", vars: { title: "t" } });
    await runScript(ws as any, "a", "repo-a", "run");
    await rmSession(ws as any, "a", true);
    expect(ws.request.mock.calls.map((c) => c[0])).toEqual(
      ["sessions.tree", "sessions.new", "sessions.script", "sessions.rm"]);
    expect(ws.request.mock.calls[2][1]).toEqual({ id: "a", repo: "repo-a", name: "run" });
    expect(ws.request.mock.calls[3][1]).toEqual({ id: "a", force: true });
  });

  it("onSessionsChanged suscribe y desuscribe", () => {
    const ws = fakeWs(); const cb = vi.fn();
    const off = onSessionsChanged(ws as any, cb);
    ws.emit("sessions.changed", { sessions: [] });
    expect(cb).toHaveBeenCalledWith({ sessions: [] });
    off();
    expect(ws.off).toHaveBeenCalledWith("sessions.changed", expect.any(Function));
  });
});
