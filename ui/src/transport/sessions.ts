import type { WsClient } from "./ws";
import type { Repo } from "./envelope";

export interface SessionNode {
  id: string; name: string; slug?: string; status: "running" | "idle" | "done";
  role?: string | null; repoId?: string | null; branch?: string | null;
  access?: "rw" | "ro" | null; worktreePath?: string | null;
  expanded: boolean; children: SessionNode[];
}
export interface Branch { name: string; occupied: boolean; }

export interface CreatePayload {
  name: string; description?: string; role?: string | null; parentId?: string | null;
  kind: "coordinator" | "work"; repoId?: string; branch?: string; base?: string;
  access?: "rw" | "ro";
}

export function fetchTree(ws: WsClient): Promise<{ sessions: SessionNode[]; repos: Repo[] }> {
  return ws.request("sessions.tree", {});
}
export function createSession(ws: WsClient, payload: CreatePayload): Promise<{ session: SessionNode }> {
  return ws.request("sessions.create", payload);
}
export function renameSession(ws: WsClient, id: string, name: string): Promise<{ renamed: boolean }> {
  return ws.request("sessions.rename", { id, name });
}
export function closeSession(ws: WsClient, id: string, force = false): Promise<{ closed: boolean }> {
  return ws.request("sessions.close", { id, force });
}
export async function fetchBranches(ws: WsClient, repoId: string): Promise<Branch[]> {
  return (await ws.request("sessions.branches", { repoId })).branches;
}
