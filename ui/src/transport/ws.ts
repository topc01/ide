import type { Envelope } from "./envelope";

export class WsClient {
  private ws: WebSocket;
  private pending = new Map<string, (p: any) => void>();
  private listeners = new Map<string, ((p: any) => void)[]>();
  private openP: Promise<void>;

  constructor(url: string) {
    this.ws = new WebSocket(url);
    this.openP = new Promise((r) => (this.ws.onopen = () => r()));
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data) as Envelope);
  }
  ready() { return this.openP; }

  private onMessage(msg: Envelope) {
    if ((msg.type === "res" || msg.type === "error") && msg.id) {
      this.pending.get(msg.id)?.(msg.type === "error" ? Promise.reject(msg.payload) : msg.payload);
      this.pending.delete(msg.id);
    } else if (msg.type === "event") {
      (this.listeners.get(msg.channel) ?? []).forEach((cb) => cb(msg.payload));
    }
  }
  request(channel: string, payload: any): Promise<any> {
    const id = crypto.randomUUID();
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.ws.send(JSON.stringify({ type: "req", id, channel, payload }));
    });
  }
  on(channel: string, cb: (p: any) => void) {
    this.listeners.set(channel, [...(this.listeners.get(channel) ?? []), cb]);
  }
}
