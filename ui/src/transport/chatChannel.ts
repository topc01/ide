import type { WsClient } from "./ws";

export function startChat(ws: WsClient, sessionId: string, override?: string): Promise<any> {
  return ws.request("chat.start", override ? { sessionId, override } : { sessionId });
}
export function sendChat(ws: WsClient, sessionId: string, text: string,
  route?: "local" | "claude"): Promise<any> {
  return ws.request("chat.send", route ? { sessionId, text, route } : { sessionId, text });
}
export function interruptChat(ws: WsClient, sessionId: string): Promise<any> {
  return ws.request("chat.interrupt", { sessionId });
}
export function permissionDecision(ws: WsClient, sessionId: string,
  requestId: string, allow: boolean): Promise<any> {
  return ws.request("chat.permission", { sessionId, requestId, allow });
}
export function subscribeChat(ws: WsClient, sessionId: string,
  onEvent: (e: any) => void): () => void {
  const channel = `chat.event.${sessionId}`;
  ws.on(channel, onEvent);
  return () => ws.off(channel, onEvent);
}
