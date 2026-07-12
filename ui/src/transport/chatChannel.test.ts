import { describe, it, expect, vi } from "vitest";
import { startChat, sendChat, permissionDecision, subscribeChat } from "./chatChannel";

function fakeWs() {
  const listeners: Record<string, (p: any) => void> = {};
  return {
    request: vi.fn((_c: string, _p: any) => Promise.resolve({ started: true })),
    on: (ch: string, cb: (p: any) => void) => { listeners[ch] = cb; },
    _emit: (ch: string, p: any) => listeners[ch]?.(p),
  } as any;
}

describe("chatChannel", () => {
  it("startChat pasa el payload", async () => {
    const ws = fakeWs();
    await startChat(ws, "s1");
    expect(ws.request).toHaveBeenCalledWith("chat.start", { sessionId: "s1" });
  });
  it("sendChat y permissionDecision pasan el payload", async () => {
    const ws = fakeWs();
    await sendChat(ws, "s1", "hola");
    expect(ws.request).toHaveBeenCalledWith("chat.send", { sessionId: "s1", text: "hola" });
    await permissionDecision(ws, "s1", "r1", true);
    expect(ws.request).toHaveBeenCalledWith("chat.permission",
      { sessionId: "s1", requestId: "r1", allow: true });
  });
  it("subscribeChat rutea eventos del canal de la sesión", () => {
    const ws = fakeWs(); const got: any[] = [];
    subscribeChat(ws, "s1", (e) => got.push(e));
    ws._emit("chat.event.s1", { kind: "text_delta", text: "hi" });
    expect(got[0]).toEqual({ kind: "text_delta", text: "hi" });
  });
});
