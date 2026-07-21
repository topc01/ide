import { WsClient } from "./ws";
import { wsUrl } from "./wsUrl";

let client: WsClient | null = null;
export function getWs(): WsClient {
  if (!client) client = new WsClient(wsUrl(import.meta.env, window.location));
  return client;
}

