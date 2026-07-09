import { WsClient } from "./ws";

let client: WsClient | null = null;
export function getWs(): WsClient {
  if (!client) client = new WsClient("ws://localhost:8787/ws");
  return client;
}
