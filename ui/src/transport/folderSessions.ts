import type { WsClient } from "./ws";
import type { Repo } from "./envelope";

export type Kind = "main" | "ticket" | "review";
export type Process = "running" | "queued" | "stopped";
export interface RepoInfo {
  name: string; state: "ok" | "missing"; branch: string | null;
  port: number | null; setup: "ok" | "failed" | null;
}
export interface FolderSession {
  id: string; kind: Kind | null; path: string; created: string; permissions: string | null;
  title: string | null; status: string | null; meta: Record<string, string>; repos: RepoInfo[];
  error: string | null; process: Process; terminalId: string | null; launchError?: string | null;
  prUrl?: string | null; reviewedSha?: string | null;
  prState?: "stale" | "merged" | "closed" | null; pollError?: string | null; lastOk?: string | null;
  attention?: string | null;      // "trust": claude espera que confirmes la carpeta
}
export interface ScriptInfo { name: string; executable: boolean; }
export interface SessionsTree {
  sessions: FolderSession[]; workspaceRepos: Repo[]; scripts: Record<string, ScriptInfo[]>;
}
export interface NewSessionReq {
  id?: string; main?: boolean; title?: string; template?: string;
  vars?: Record<string, string>; prompt?: string;
  permissions?: "analyze" | "full" | "default"; review?: string;
  notion?: string; if_missing?: boolean; dry_run?: boolean;
}

export const fetchSessions = (ws: WsClient): Promise<SessionsTree> => ws.request("sessions.tree", {});
export const newSession = (ws: WsClient, req: NewSessionReq) => ws.request("sessions.new", req);
export const openSession = (ws: WsClient, id: string) => ws.request("sessions.open", { id });
export const stopSession = (ws: WsClient, id: string) => ws.request("sessions.stop", { id });
export const archiveSession = (ws: WsClient, id: string, force = false) =>
  ws.request("sessions.archive", { id, force });
export const rmSession = (ws: WsClient, id: string, force = false) =>
  ws.request("sessions.rm", { id, force });
export const runScript = (ws: WsClient, id: string, repo: string, name: string):
  Promise<{ terminalId: string }> => ws.request("sessions.script", { id, repo, name });
export const fetchDoc = (ws: WsClient, id: string): Promise<{ name: string; text: string }> =>
  ws.request("sessions.doc", { id });
export const refreshReview = (ws: WsClient, id: string) => ws.request("sessions.refreshReview", { id });
export const rmRepo = (ws: WsClient, id: string, repo: string, force = false) =>
  ws.request("sessions.repoRm", { id, repo, force });
export interface PromptInfo { name: string; text: string; }
export const fetchPrompts = (ws: WsClient): Promise<{ prompts: PromptInfo[] }> =>
  ws.request("prompts.list", {});
export const fetchUiConfig = (ws: WsClient): Promise<{ modules: string[] }> => ws.request("ui.config", {});

export function onSessionsChanged(ws: WsClient, cb: (t: SessionsTree) => void): () => void {
  const handler = (p: SessionsTree) => cb(p);
  ws.on("sessions.changed", handler);
  return () => ws.off("sessions.changed", handler);
}

export interface GhPr {
  url: string; title: string; number: number; repo: string; author: string;
  draft: boolean; updatedAt: string | null; sessionId: string;
  head: string | null; base: string | null;
  review: "approved" | "changes" | "review" | null;
  stack: { id: string; position: number; size: number } | null;
  reviewers?: { login: string; state: "requested" | "approved" | "changes" }[];
  ci?: "success" | "failure" | "pending" | null; conflict?: boolean;
}
export interface GithubReviews {
  pending: GhPr[]; changesRequested: GhPr[]; error: string | null; lastOk: string | null; orgs: string[];
  me: string | null; reviewers: { login: string; count: number }[]; reviewersTruncated: boolean;
  members: { login: string; name: string | null }[]; selected: string[] | null;
  mine: Partial<Record<"returned" | "waiting" | "missing" | "draft" | "approved", GhPr[]>>;
  stacks?: Record<string, GhPr[]>;      // id del stack -> PRs de abajo hacia arriba
  merges?: Record<string, MergeJob>;    // url -> merge armado desde el IDE
}
export const fetchGithubReviews = (ws: WsClient): Promise<GithubReviews> => ws.request("reviews.github", {});
export const startReview = (ws: WsClient, url: string): Promise<{ id: string; created: boolean; process: Process }> =>
  ws.request("reviews.start", { url });
export interface MergeJob {
  state: "waiting" | "restacking" | "done" | "error"; error: string | null; restacked: string[] | null;
  repo?: string; number?: number; title?: string; above?: { url: string }[];
}
export const mergePr = (ws: WsClient, url: string): Promise<MergeJob> => ws.request("reviews.merge", { url });
export const retryMerge = (ws: WsClient, url: string) => ws.request("reviews.mergeRetry", { url });
export const setReviewers = (ws: WsClient, logins: string[]): Promise<GithubReviews> =>
  ws.request("reviews.setReviewers", { logins });
export function onGithubReviews(ws: WsClient, cb: (r: GithubReviews) => void): () => void {
  const handler = (p: GithubReviews) => cb(p);
  ws.on("reviews.github", handler);
  return () => ws.off("reviews.github", handler);
}

export interface UsageWindow { percent: number; resetsAt: string | null; }
export interface Usage {
  context: { used: number; window: number; model: string | null } | null;
  limits: { fiveHour: UsageWindow | null; weekly: UsageWindow | null; error: string | null; lastOk: string | null };
}
export const fetchUsage = (ws: WsClient, sessionId: string | null): Promise<Usage> =>
  ws.request("usage.get", { sessionId });
