import { describe, it, expect, vi } from "vitest";
import { openTerminal, writeTerminal, subscribeTerminal } from "./terminalChannel";

function fakeWs() {
  const listeners: Record<string, (p: any) => void> = {};
  return {
    request: vi.fn((_c: string, _p: any) => Promise.resolve({ id: "t1", cwd: "/x" })),
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
});
