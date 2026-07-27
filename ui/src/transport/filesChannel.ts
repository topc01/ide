import type { WsClient } from "./ws";

export interface FileEntry { name: string; type: "dir" | "file"; }

export function listFiles(ws: WsClient, sessionId: string, path: string): Promise<{ entries: FileEntry[] }> {
  return ws.request("files.list", { sessionId, path });
}
export function openFile(ws: WsClient, sessionId: string, path: string, line?: number): Promise<{ id: string; cwd: string }> {
  return ws.request("files.open", line ? { sessionId, path, line } : { sessionId, path });
}
