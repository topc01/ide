import type { WsClient } from "./ws";

export interface FileChange { path: string; status: string; added: number | null; removed: number | null }
export interface RepoStatus {
  name: string; path: string; branch: string; head: string;
  files: FileChange[]; totalAdded: number; totalRemoved: number;
}
export type DiffLineType = "hunk" | "add" | "del" | "ctx";
export interface DiffLine { type: DiffLineType; text: string }

export async function fetchChanges(
  ws: WsClient, opts: { sessionId?: string | null },
): Promise<RepoStatus> {
  return (await ws.request("changes.list", { sessionId: opts.sessionId ?? undefined })).status;
}

export async function fetchDiff(
  ws: WsClient, opts: { sessionId?: string | null; path: string; status: string },
): Promise<DiffLine[]> {
  return (await ws.request("changes.diff", {
    sessionId: opts.sessionId ?? undefined, path: opts.path, status: opts.status,
  })).lines;
}
