import type { WsClient } from "./ws";
import type { FileChange } from "./changesChannel";

export interface StackBranch {
  name: string; parent: string | null; isTrunk: boolean;
  current: boolean; needsRestack: boolean; revision: string;
}
export interface Commit { hash: string; message: string; files: FileChange[] }

export async function fetchStack(
  ws: WsClient, opts: { sessionId?: string | null },
): Promise<{ stack: StackBranch[]; current: string }> {
  return ws.request("graphite.stack", { sessionId: opts.sessionId ?? undefined });
}

export async function fetchBranch(
  ws: WsClient, opts: { sessionId?: string | null; branch: string },
): Promise<Commit[]> {
  return (await ws.request("graphite.branch",
    { sessionId: opts.sessionId ?? undefined, branch: opts.branch })).commits;
}

export async function restackBranch(
  ws: WsClient, opts: { sessionId?: string | null; branch: string },
): Promise<{ stack: StackBranch[]; current: string }> {
  return ws.request("graphite.restack", { sessionId: opts.sessionId ?? undefined, branch: opts.branch });
}
