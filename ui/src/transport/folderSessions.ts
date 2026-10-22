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
  stackPrs?: string[] | null;     // revisión de un stack: sus PRs, de abajo hacia arriba
  // actividad de su claude (hooks): trabajando o esperando tu input (nota = 1ª línea de su último mensaje)
  activity?: { state: "working" | "waiting"; since: string; note: string | null; reason: string | null } | null;
}
export interface ScriptInfo { name: string; executable: boolean; }
export interface SessionsTree {
  sessions: FolderSession[]; workspaceRepos: Repo[]; scripts: Record<string, ScriptInfo[]>;
  devNames?: Record<string, string>;    // nombre puesto en el IDE, por clave de desarrollo (s:/st:/p:)
  devHidden?: string[];                 // desarrollos ocultos en Mis desarrollos (grupo "Ocultos")
  devPrs?: PrLinks;                     // PRs vinculadas a una sesión (siguen aunque cambie la rama)
  devIndex?: Record<string, number>;    // número de cada desarrollo (#12), por clave
  devStates?: Record<string, { phase?: string | null; block?: string | null; note?: string | null; since?: string | null }>;   // fase + bloqueo
  feedbackPending?: string[];            // planes de feedback de la manager sin revisar
  later?: LaterItem[];                  // pendientes para después, abiertos
}
/** Pendiente "para después" de un desarrollo (lo deja la sesión con `ide later add` o el usuario). */
export interface LaterItem {
  id: string; key: string; text: string; context: string | null; actor: string; created: string;
  status: "open" | "answered" | "resolved" | "dismissed"; answer: string | null; resolved: string | null;
}
export const laterAdd = (ws: WsClient, key: string, text: string, context: string | null): Promise<{ item: LaterItem }> =>
  ws.request("later.add", { key, text, context });
/** Responder: si el desarrollo tiene sesión, la respuesta se le manda (`delivered` dice cómo). */
export const laterAnswer = (ws: WsClient, id: string, answer: string): Promise<{ ok: boolean; delivered: string }> =>
  ws.request("later.answer", { id, answer });
/** Cerrar como resuelto sin mandarle nada a la sesión (se resolvió en el chat). */
export const laterResolve = (ws: WsClient, id: string, note: string | null = null): Promise<{ ok: boolean }> =>
  ws.request("later.resolve", { id, note });
export const laterDismiss = (ws: WsClient, id: string): Promise<{ ok: boolean }> => ws.request("later.dismiss", { id });
/** Estado del desarrollo (local); `status` null = sin estado. */
/** `gh`: la fase de GitHub al ponerla a mano (la puesta gana hasta que GitHub cambie); sin `gh` manda GitHub. */
export const setDevState = (ws: WsClient, key: string, status: string | null, note: string | null, gh?: string | null): Promise<{ ok: boolean }> =>
  ws.request("dev.state", { key, status, note, ...(gh !== undefined ? { gh } : {}) });
/** "Mandar a revisión": saca de draft las PRs (`gh pr ready`). */
export const prsReady = (ws: WsClient, urls: string[]): Promise<{ ready: string[]; errors: string[] }> =>
  ws.request("prs.ready", { urls });
export interface PrFile { path: string; oldPath: string | null; status: string; additions: number; deletions: number }
/** Archivos cambiados de una PR contra su base (en un stack, la PR de abajo). */
export const prFiles = (ws: WsClient, url: string, fresh = false): Promise<{ files: PrFile[]; base: string; mergeBase: string; local: string | null }> =>
  ws.request("pr.files", { url, fresh });
export const prFileDiff = (ws: WsClient, url: string, path: string, oldPath: string | null): Promise<{ old: string | null; new: string | null; local: boolean }> =>
  ws.request("pr.fileDiff", { url, path, oldPath });
/** Rebasea el stack de la PR (y la de abajo sobre su base si `updateBase`) y empuja con --force-with-lease. */
/** Qué necesita el stack de esa PR: ramas que quedaron atrás de su madre y commits nuevos en la base. */
export const stackStatus = (ws: WsClient, url: string): Promise<{ behindParent: string[]; baseAhead: number; base: string | null }> =>
  ws.request("stack.status", { url });
export const restackStack = (ws: WsClient, url: string, updateBase: boolean): Promise<{ moved: string[] }> =>
  ws.request("stack.restack", { url, updateBase });
/** El veredicto de la sesión de revisión de una PR y su review listo para publicar (de su SESSION.md). */
export const reviewDraft = (ws: WsClient, url: string): Promise<{ id: string | null; verdict: "approve" | "request-changes" | null; why: string; body: string }> =>
  ws.request("review.draft", { url });
/** Publica TU review en GitHub (`gh pr review --approve | --request-changes`). */
export const reviewSubmit = (ws: WsClient, url: string, event: "approve" | "request-changes", body: string): Promise<{ ok: boolean }> =>
  ws.request("review.submit", { url, event, body });
/** Pedir revisión a / sacar revisores de una PR tuya (`gh pr edit`). */
export const prReviewers = (ws: WsClient, url: string, add: string[], remove: string[] = []): Promise<{ ok: boolean }> =>
  ws.request("pr.reviewers", { url, add, remove });
export interface Pin { id: string; text: string; source: string | null; at: string }
/** Últimos mensajes de claude de una sesión (del transcript: texto limpio). */
export const sessionMessages = (ws: WsClient, id: string, limit = 15): Promise<{ messages: { id: string; at: string | null; text: string }[] }> =>
  ws.request("session.messages", { id, limit });
export const listPins = (ws: WsClient): Promise<{ pins: Record<string, Pin[]> }> => ws.request("pins.list", {});
export const addPin = (ws: WsClient, key: string, text: string, source: string | null): Promise<{ pin: Pin }> =>
  ws.request("pins.add", { key, text, source });
export const removePin = (ws: WsClient, key: string, id: string): Promise<{ ok: boolean }> => ws.request("pins.remove", { key, id });
/** Adjuntar un archivo a la conversación de una sesión (se guarda en su carpeta y se pega su ruta). */
export const attachFile = (ws: WsClient, id: string, name: string, data: string, paste = true): Promise<{ path: string; pasted: boolean }> =>
  ws.request("sessions.attach", { id, name, data, paste });
export interface Attachment { name: string; size: number; path: string; at: string; kind: "image" | "pdf" | "text" | "other"; url: string | null }
/** Guardar un link como adjunto (`.url`). */
export const addLinkAttachment = (ws: WsClient, id: string, url: string, name: string): Promise<{ name: string }> =>
  ws.request("attachments.link", { id, url, name });
export const listAttachments = (ws: WsClient, id: string): Promise<{ dir: string; files: Attachment[] }> =>
  ws.request("attachments.list", { id });
export const renameAttachment = (ws: WsClient, id: string, name: string, to: string): Promise<{ name: string }> =>
  ws.request("attachments.rename", { id, name, to });
export const deleteAttachment = (ws: WsClient, id: string, name: string): Promise<{ ok: boolean }> =>
  ws.request("attachments.delete", { id, name });
export const attachmentUrl = (sid: string, name: string, download = false) =>
  `/api/sessions/${encodeURIComponent(sid)}/attachments/${encodeURIComponent(name)}${download ? "?download=1" : ""}`;
export type PrLinks = Record<string, { sid: string; out?: boolean }>;
/** Saca una PR del desarrollo de una sesión (no vuelve aunque el worktree esté en su rama). */
/** Asigna PRs a un desarrollo (sesión): pisa la asignación que tuvieran. */
export const linkPr = (ws: WsClient, id: string, prs: string[]): Promise<{ ok: boolean; moved: { pr: string; from: string; to: string; warning: string | null }[] }> =>
  ws.request("dev.linkPr", { id, prs });
export const unlinkPr = (ws: WsClient, id: string, url: string): Promise<{ ok: boolean }> =>
  ws.request("dev.unlinkPr", { id, url });
/** Ocultar / volver a mostrar un desarrollo en Mis desarrollos (solo el IDE). */
export const hideDev = (ws: WsClient, key: string, hidden: boolean): Promise<{ ok: boolean }> =>
  ws.request("dev.hide", { key, hidden });
/** Nombre del desarrollo solo para el IDE; `name` vacío = volver al original. */
export const renameDev = (ws: WsClient, key: string, name: string): Promise<{ ok: boolean }> =>
  ws.request("dev.rename", { key, name });
export interface NewSessionReq {
  id?: string; main?: boolean; title?: string; template?: string;
  vars?: Record<string, string>; prompt?: string;
  permissions?: "analyze" | "full" | "default"; review?: string;
  notion?: string; if_missing?: boolean; dry_run?: boolean;
}

export const fetchSessions = (ws: WsClient): Promise<SessionsTree> => ws.request("sessions.tree", {});
export const newSession = (ws: WsClient, req: NewSessionReq) => ws.request("sessions.new", req);
/** Sesión para seguir trabajando una PR propia (worktree en su rama), en el mismo desarrollo. */
export const newSessionForPr = (ws: WsClient, url: string): Promise<{ session: FolderSession }> =>
  ws.request("sessions.newForPr", { url });
export const fetchPrBody = (ws: WsClient, url: string): Promise<{ body: string; state: string }> =>
  ws.request("pr.body", { url });
export const savePrBody = (ws: WsClient, url: string, body: string) => ws.request("pr.bodySave", { url, body });
export const openSession = (ws: WsClient, id: string) => ws.request("sessions.open", { id });
export const stopSession = (ws: WsClient, id: string) => ws.request("sessions.stop", { id });
/** Nueva conversación en la misma sesión (misma carpeta, worktrees y SESSION.md). */
export const freshSession = (ws: WsClient, id: string): Promise<{ process: string }> => ws.request("sessions.fresh", { id });
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
  stack: { id: string; position: number; size: number; native?: boolean } | null;
  reviewers?: { login: string; state: "requested" | "approved" | "changes" }[];
  ci?: "success" | "failure" | "pending" | null; conflict?: boolean;
  deps?: PrDep[]; depsPending?: number;     // dependencias declaradas en "## Dependencias"
  merged?: boolean;                         // solo en `closed`: ya no está abierta (true = mergeada)
}
/** Dependencia (directa o transitiva, `via` = por cuál directa se llega) de una PR. */
export interface PrDep {
  url: string; repo: string | null; number: number | null; title: string | null;
  state: "OPEN" | "MERGED" | "CLOSED" | "UNKNOWN"; via: string | null; together: boolean;
}
export interface GithubReviews {
  pending: GhPr[]; changesRequested: GhPr[]; error: string | null; lastOk: string | null; orgs: string[];
  me: string | null; reviewers: { login: string; count: number }[]; reviewersTruncated: boolean;
  members: { login: string; name: string | null }[]; selected: string[] | null;
  mine: Partial<Record<"returned" | "waiting" | "missing" | "draft" | "approved", GhPr[]>>;
  stacks?: Record<string, GhPr[]>;      // id del stack -> PRs de abajo hacia arriba
  merges?: Record<string, MergeJob>;    // url -> merge armado desde el IDE
  closed?: GhPr[];                      // PRs de desarrollos con sesión que ya se cerraron/mergearon
}
export const fetchGithubReviews = (ws: WsClient): Promise<GithubReviews> => ws.request("reviews.github", {});
/** "Revisar stack": una sesión para varias PRs pendientes de un stack (archiva las individuales). */
export const startStackReview = (ws: WsClient, urls: string[]): Promise<{ id: string; created: boolean; process: Process }> =>
  ws.request("reviews.startStack", { urls });
export const startReview = (ws: WsClient, url: string): Promise<{ id: string; created: boolean; process: Process }> =>
  ws.request("reviews.start", { url });
export interface MergeJob {
  state: "rebasing" | "waiting" | "waiting_ci" | "merging" | "restacking" | "done" | "error";
  error: string | null; restacked: string[] | null;
  repo?: string; number?: number; title?: string; above?: { url: string }[];
  native?: boolean; merged_at?: string | null; url?: string;
}
export const mergePr = (ws: WsClient, url: string): Promise<MergeJob> => ws.request("reviews.merge", { url });
export const dismissMerge = (ws: WsClient, url: string) => ws.request("reviews.mergeDismiss", { url });
export const retryMerge = (ws: WsClient, url: string) => ws.request("reviews.mergeRetry", { url });
export interface Discussion {
  url: string; title: string; number: number; state: "OPEN" | "MERGED" | "CLOSED"; draft: boolean;
  decision: string | null; conflict: boolean; head: string; base: string;
  ci: "success" | "failure" | "pending" | null;
  checks: { name: string | null; url: string | null; state: "success" | "failure" | "pending" }[];
  reviewers: { login: string; state: string }[];
  conversation: { kind: "review" | "comment"; author: string; state: string | null; body: string;
                  at: string | null; url: string | null }[];
  threads: { resolved: boolean; outdated: boolean; path: string | null; line: number | null;
             comments: { author: string; body: string; at: string | null; url: string | null }[] }[];
}
export const fetchDiscussion = (ws: WsClient, url: string): Promise<Discussion> =>
  ws.request("reviews.discussion", { url });
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

/** Evidencias: pasos de prueba con capturas (módulo Evidencias). */
export interface EvidenceStep { id: string; title: string; detail: string; shot: boolean; shots: string[]; done: boolean }
export interface EvidenceRun { id: string; label: string; created: string; steps: EvidenceStep[] }
export const evidenceList = (ws: WsClient, id: string): Promise<{ runs: EvidenceRun[] }> => ws.request("evidence.list", { id });
export const evidenceNew = (ws: WsClient, id: string, label: string, steps: Partial<EvidenceStep>[] = []): Promise<{ run: EvidenceRun }> =>
  ws.request("evidence.new", { id, label, steps });
export const evidenceSave = (ws: WsClient, id: string, run: EvidenceRun): Promise<{ run: EvidenceRun }> => ws.request("evidence.save", { id, run });
export const evidenceDuplicate = (ws: WsClient, id: string, run: string, label: string): Promise<{ run: EvidenceRun }> =>
  ws.request("evidence.duplicate", { id, run, label });
export const evidenceDelete = (ws: WsClient, id: string, run: string): Promise<{ ok: boolean }> => ws.request("evidence.delete", { id, run });
export const evidenceShot = (ws: WsClient, id: string, run: string, step: string, name: string, data: string): Promise<{ run: EvidenceRun }> =>
  ws.request("evidence.shot", { id, run, step, name, data });
export const evidenceMarkdown = (ws: WsClient, id: string, run: string): Promise<{ markdown: string }> => ws.request("evidence.markdown", { id, run });
export const evidenceGithub = (ws: WsClient, id: string, run: string, url: string): Promise<{ ok: boolean; comment: string }> =>
  ws.request("evidence.github", { id, run, url });
