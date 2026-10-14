import type { Envelope } from "./envelope";

interface Pending {
  resolve: (p: any) => void;
  reject: (p: any) => void;
}

export class WsClient {
  private ws: WebSocket;
  private pending = new Map<string, Pending>();
  private listeners = new Map<string, ((p: any) => void)[]>();
  private openP: Promise<void>;
  private closeListeners: (() => void)[] = [];

  constructor(url: string) {
    this.ws = new WebSocket(url);
    this.openP = new Promise<void>((resolve, reject) => {
      this.ws.onopen = () => resolve();
      this.ws.onerror = () => reject(new Error("WebSocket error antes de abrir"));
      this.ws.onclose = () => {
        reject(new Error("WebSocket cerrado antes de abrir"));   // no-op si ya abrió
        // nunca dejar requests colgados: el server ya no va a responder
        const lost = { code: "disconnected", message: "conexión con el server perdida" };
        this.pending.forEach((p) => p.reject(lost));
        this.pending.clear();
        this.closeListeners.forEach((cb) => cb());
      };
    });
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data) as Envelope);
  }
  ready() { return this.openP; }
  onClose(cb: () => void) { this.closeListeners.push(cb); }

  private onMessage(msg: Envelope) {
    if ((msg.type === "res" || msg.type === "error") && msg.id) {
      const entry = this.pending.get(msg.id);
      if (msg.type === "error") entry?.reject(msg.payload);
      else entry?.resolve(msg.payload);
      this.pending.delete(msg.id);
    } else if (msg.type === "event") {
      (this.listeners.get(msg.channel) ?? []).forEach((cb) => cb(msg.payload));
    }
  }
  request(channel: string, payload: any): Promise<any> {
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      // Diferir el envío hasta que el socket abra: si se llama antes (p.ej. un
      // fetch al montar, sin await ready()), send() sobre un socket CONNECTING
      // lanza. Un fallo del envío rechaza el request, nunca silencioso.
      this.openP
        .then(() => this.ws.send(JSON.stringify({ type: "req", id, channel, payload })))
        .catch(reject);
    });
  }
  on(channel: string, cb: (p: any) => void) {
    this.listeners.set(channel, [...(this.listeners.get(channel) ?? []), cb]);
  }
  off(channel: string, cb: (p: any) => void) {
    const next = (this.listeners.get(channel) ?? []).filter((l) => l !== cb);
    if (next.length === 0) this.listeners.delete(channel);
    else this.listeners.set(channel, next);
  }
}
