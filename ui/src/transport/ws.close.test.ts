import { describe, it, expect, vi } from "vitest";
import { WsClient } from "./ws";

class FakeSocket {
  static last: FakeSocket;
  onopen: any; onclose: any; onerror: any; onmessage: any;
  constructor() { FakeSocket.last = this; }
  send() {}
}

describe("WsClient.onClose", () => {
  it("avisa cuando el socket se cierra después de abrir", async () => {
    vi.stubGlobal("WebSocket", FakeSocket as any);
    const ws = new WsClient("ws://x");
    const cb = vi.fn();
    ws.onClose(cb);
    FakeSocket.last.onopen();
    await ws.ready();
    FakeSocket.last.onclose();
    expect(cb).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("rechaza los requests pendientes al perder la conexión", async () => {
    vi.stubGlobal("WebSocket", FakeSocket as any);
    vi.stubGlobal("crypto", { randomUUID: () => "id-1" });
    const ws = new WsClient("ws://x");
    FakeSocket.last.onopen();
    await ws.ready();
    const p = ws.request("sessions.tree", {});
    FakeSocket.last.onclose();
    await expect(p).rejects.toEqual({ code: "disconnected", message: "conexión con el server perdida" });
    vi.unstubAllGlobals();
  });
});
