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

describe("WsClient", () => {
  beforeEach(() => { (globalThis as any).WebSocket = FakeSocket; });
  it("correlaciona req/res por id", async () => {
    const c = new WsClient("ws://x/ws"); await c.ready();
    expect(await c.request("t.inc", { n: 5 })).toEqual({ ok: 5 });
  });

  it("rechaza el request cuando el server responde con frame error", async () => {
    (globalThis as any).WebSocket = FakeErrorSocket;
    const c = new WsClient("ws://x/ws"); await c.ready();
    await expect(c.request("t.inc", { n: 5 })).rejects.toEqual({ code: "BOOM", message: "algo falló" });
  });
});
