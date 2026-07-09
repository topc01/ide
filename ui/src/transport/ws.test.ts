import { describe, it, expect, beforeEach } from "vitest";
import { WsClient } from "./ws";

class FakeSocket {
  onopen: any; onmessage: any; onclose: any; sent: string[] = [];
  constructor(public url: string) { setTimeout(() => this.onopen?.(), 0); }
  send(s: string) {
    this.sent.push(s);
    const req = JSON.parse(s);
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(
      { type: "res", id: req.id, channel: req.channel, payload: { ok: req.payload.n } }) }), 0);
  }
  close() { this.onclose?.(); }
}

class FakeErrorSocket {
  onopen: any; onmessage: any; onclose: any; sent: string[] = [];
  constructor(public url: string) { setTimeout(() => this.onopen?.(), 0); }
  send(s: string) {
    this.sent.push(s);
    const req = JSON.parse(s);
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(
      { type: "error", id: req.id, channel: req.channel, payload: { code: "BOOM", message: "algo falló" } }) }), 0);
  }
  close() { this.onclose?.(); }
}

class FakeFailSocket {
  onopen: any; onmessage: any; onclose: any; onerror: any; sent: string[] = [];
  constructor(public url: string) { setTimeout(() => this.onclose?.(), 0); }   // cierra sin abrir
  send() { throw new Error("no debería enviarse"); }
  close() {}
}

class FakeConnectingSocket {
  onopen: any; onmessage: any; onclose: any; sent: string[] = [];
  private open = false;
  constructor(public url: string) { setTimeout(() => { this.open = true; this.onopen?.(); }, 0); }
  send(s: string) {
    if (!this.open) throw new Error("Still in CONNECTING state");   // como un WebSocket real
    this.sent.push(s);
    const req = JSON.parse(s);
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(
      { type: "res", id: req.id, channel: req.channel, payload: { ok: req.payload.n } }) }), 0);
  }
  close() { this.onclose?.(); }
}

describe("WsClient", () => {
  beforeEach(() => { (globalThis as any).WebSocket = FakeSocket; });
  it("correlaciona req/res por id", async () => {
    const c = new WsClient("ws://x/ws"); await c.ready();
    expect(await c.request("t.inc", { n: 5 })).toEqual({ ok: 5 });
  });

  it("difiere el send hasta que el socket abre (request sin await ready)", async () => {
    (globalThis as any).WebSocket = FakeConnectingSocket;
    const c = new WsClient("ws://x/ws");   // NO await ready(), como SessionsPanel al montar
    expect(await c.request("t.inc", { n: 7 })).toEqual({ ok: 7 });
  });

  it("rechaza el request cuando el server responde con frame error", async () => {
    (globalThis as any).WebSocket = FakeErrorSocket;
    const c = new WsClient("ws://x/ws"); await c.ready();
    await expect(c.request("t.inc", { n: 5 })).rejects.toEqual({ code: "BOOM", message: "algo falló" });
  });

  it("rechaza el request si el socket cierra antes de abrir (no cuelga)", async () => {
    (globalThis as any).WebSocket = FakeFailSocket;
    const c = new WsClient("ws://x/ws");
    await expect(c.request("t.inc", { n: 1 })).rejects.toThrow();
  });
});
