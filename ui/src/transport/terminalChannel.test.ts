import { describe, it, expect, vi } from "vitest";
import { openTerminal, writeTerminal, subscribeTerminal, listTerminals } from "./terminalChannel";

function fakeWs(resp: any = { id: "t1", cwd: "/x" }) {
  const listeners: Record<string, (p: any) => void> = {};
  return {
    request: vi.fn((_c: string, _p: any) => Promise.resolve(resp)),
    on: (ch: string, cb: (p: any) => void) => { listeners[ch] = cb; },
    _emit: (ch: string, p: any) => listeners[ch]?.(p),
  } as any;
}

describe("terminalChannel", () => {
  it("openTerminal pasa el payload por el canal", async () => {
    const ws = fakeWs();
    expect(await openTerminal(ws, { repoId: "repoA" })).toEqual({ id: "t1", cwd: "/x" });
    expect(ws.request).toHaveBeenCalledWith("terminal.open", { repoId: "repoA" });
  });
  it("writeTerminal codifica a base64", async () => {
    const ws = fakeWs();
    await writeTerminal(ws, "t1", "hi");
    expect(ws.request).toHaveBeenCalledWith("terminal.write", { id: "t1", data: btoa("hi") });
  });
  it("subscribeTerminal decodifica base64 a bytes", () => {
    const ws = fakeWs();
    const chunks: Uint8Array[] = [];
    subscribeTerminal(ws, "t1", (b) => chunks.push(b), () => {});
    ws._emit("terminal.data.t1", { data: btoa("AB") });
    expect(Array.from(chunks[0])).toEqual([65, 66]);
  });
  it("listTerminals pide terminal.list con sessionId y devuelve el array", async () => {
    const ws = fakeWs({ terminals: [{ id: "term-1", cmd: ["zsh"], alive: true }] });
    expect(await listTerminals(ws, "s1")).toEqual([{ id: "term-1", cmd: ["zsh"], alive: true }]);
    expect(ws.request).toHaveBeenCalledWith("terminal.list", { sessionId: "s1" });
  });
});
