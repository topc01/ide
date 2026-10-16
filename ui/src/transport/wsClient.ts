import { WsClient } from "./ws";
import { wsUrl } from "./wsUrl";

let client: WsClient | null = null;
let waiting = false;

/** Se cortó el server (p.ej. se reinició con una versión nueva): esperar a que vuelva y recargar
 *  la página (trae la UI nueva y re-suscribe todo; el desarrollo abierto se recuerda). */
function reloadWhenBack() {
  if (waiting) return;
  waiting = true;
  const tick = () => fetch("/health", { cache: "no-store" })
    .then((r) => (r.ok ? window.location.reload() : setTimeout(tick, 1500)))
    .catch(() => setTimeout(tick, 1500));
  setTimeout(tick, 1500);
}

export function getWs(): WsClient {
  if (!client) {
    client = new WsClient(wsUrl(import.meta.env, window.location));
    if (!import.meta.env.DEV) client.onClose(reloadWhenBack);   // en dev (Vite) el server va aparte
  }
  return client;
}

