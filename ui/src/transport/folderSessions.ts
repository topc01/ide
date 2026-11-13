import { openAttachmentFile } from "../lib/openExternal";
import type { WsClient } from "./ws";
import type { Repo } from "./envelope";

export type Kind = "main" | "ticket" | "review" | "ide" | "recursos" | "plugins";   // ide: claude en el repo del IDE (pestaña junto a la manager)
export type Process = "running" | "queued" | "stopped";
export interface RepoInfo {
  name: string; state: "ok" | "missing"; branch: string | null;
  port: number | null; setup: "ok" | "failed" | null;
}
export interface FolderSession {
  id: string; kind: Kind | null; path: string; created: string; permissions: string | null; model?: string | null;
  title: string | null; status: string | null; meta: Record<string, string>; repos: RepoInfo[];
  error: string | null; process: Process; terminalId: string | null; launchError?: string | null;
  prUrl?: string | null; reviewedSha?: string | null;
  prState?: "stale" | "merged" | "closed" | null; pollError?: string | null; lastOk?: string | null;
  attention?: string | null;      // "trust": claude espera que confirmes la carpeta
  stackPrs?: string[] | null;     // revisión de un stack: sus PRs, de abajo hacia arriba
  // actividad de su claude (hooks): trabajando o esperando tu input (nota = 1ª línea de su último mensaje)
  activity?: { state: "working" | "waiting" | "outdated"; since: string; note: string | null; reason: string | null;
    /** te esperaba, pero después pasó algo en sus PRs (aprobaste, se mergeó…): su mensaje quedó viejo */
    outdated?: { what: string; at: string } } | null;
  frozen?: string | null;         // congelada (SIGSTOP) desde
  paused?: { at: string } | null; // pausada: su claude se cerró y nada lo relanza solo
  consult?: { terminalId: string; at: string } | null;   // claude de consulta abierto (solo lectura)
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
  // ticket de Notion de cada desarrollo de ticket (`s:<id>`): url (null = sin ticket), Status de la caché, pendientes
  devTickets?: Record<string, { url: string | null; status: string | null; error: string | null; title?: string | null;
    pending: { url: string; status: string | null; title: string | null }[];
    subs?: { url: string; status: string | null; title: string | null; card?: boolean }[] }>;
  // desarrollos colgados de otro (`s:<id>`): mismo ticket, PR apilada sobre una rama de otro, separado por el IDE
  verdicts?: Record<string, { verdict: "approve" | "request-changes"; at: string | null; sha: string | null }>;
  devRelations?: Record<string, { kind: "ticket" | "stacked" | "split"; dev: string; n: number | null; pr?: string }[]>;
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
export const reviewDraft = (ws: WsClient, url: string): Promise<{ id: string | null; verdict: "approve" | "request-changes" | null; why: string; body: string;
    at?: string; sha?: string | null; newCommits?: boolean }> =>
  ws.request("review.draft", { url });
/** Publica TU review en GitHub (`gh pr review --approve | --request-changes`). */
export const reviewSubmit = (ws: WsClient, url: string, event: "approve" | "request-changes", body: string): Promise<{ ok: boolean }> =>
  ws.request("review.submit", { url, event, body });
/** Pedir revisión a / sacar revisores de una PR tuya (`gh pr edit`). */
export const prReviewers = (ws: WsClient, url: string, add: string[], remove: string[] = []): Promise<{ ok: boolean }> =>
  ws.request("pr.reviewers", { url, add, remove });
/** Adjuntar un archivo a la conversación de una sesión (se guarda en su carpeta y se pega su ruta). */
/** `dir`: carpeta dentro de attachments/ donde queda (sin ella, la raíz). */
export const attachFile = (ws: WsClient, id: string, name: string, data: string, paste = true, dir?: string): Promise<{ path: string; pasted: boolean }> =>
  ws.request("sessions.attach", { id, name, data, paste, ...(dir ? { dir } : {}) });
/** `name`: ruta relativa a attachments/ (con carpetas: `facturas/marzo.pdf`); `created`: cuándo se creó. */
export interface Attachment { name: string; size: number; path: string; at: string; created: string; kind: "image" | "pdf" | "text" | "other"; url: string | null }
export const mkdirAttachment = (ws: WsClient, id: string, dir: string): Promise<{ name: string }> =>
  ws.request("attachments.mkdir", { id, dir });
/** Mueve un archivo o carpeta a `dir` ("" = la raíz). */
export const moveAttachment = (ws: WsClient, id: string, name: string, dir: string): Promise<{ name: string }> =>
  ws.request("attachments.move", { id, name, dir });
/** Guardar un link como adjunto (`.url`). */
export const addLinkAttachment = (ws: WsClient, id: string, url: string, name: string): Promise<{ name: string }> =>
  ws.request("attachments.link", { id, url, name });
export const listAttachments = (ws: WsClient, id: string): Promise<{ dir: string; files: Attachment[]; dirs: string[] }> =>
  ws.request("attachments.list", { id });
export const renameAttachment = (ws: WsClient, id: string, name: string, to: string): Promise<{ name: string }> =>
  ws.request("attachments.rename", { id, name, to });
export const deleteAttachment = (ws: WsClient, id: string, name: string): Promise<{ ok: boolean }> =>
  ws.request("attachments.delete", { id, name });
/** Un .html adjunto se abre en una pestaña del navegador (como página, aislada del IDE) en vez de una tab. */
export const isHtml = (name: string) => /\.html?$/i.test(name);
export const openHtmlAttachment = (sid: string, name: string) => openAttachmentFile(sid, name);
export const attachmentUrl = (sid: string, name: string, download = false) =>
  `/api/sessions/${encodeURIComponent(sid)}/attachments/${name.split("/").map(encodeURIComponent).join("/")}${download ? "?download=1" : ""}`;
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
  permissions?: "analyze" | "full" | "default"; review?: string; model?: string;
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
/** Congelar / soltar su claude (SIGSTOP/SIGCONT): sigue donde estaba; no libera memoria. */
export const freezeSession = (ws: WsClient, id: string, on: boolean) => ws.request("sessions.freeze", { id, on });
/** Pausar: corta el turno, cierra su claude (libera memoria) y nada lo relanza solo. Reanudar lo relanza. */
export const pauseSession = (ws: WsClient, id: string) => ws.request("sessions.pause", { id });
export const resumeSession = (ws: WsClient, id: string) => ws.request("sessions.resume", { id });
/** Claude de consulta: bifurca la conversación de la sesión en modo plan (solo lectura). */
export const openConsult = (ws: WsClient, id: string): Promise<{ terminalId: string }> => ws.request("sessions.consult", { id });
export const consultLast = (ws: WsClient, id: string): Promise<{ text: string }> => ws.request("sessions.consultLast", { id });
export const consultSend = (ws: WsClient, id: string, text: string): Promise<{ process: string; how: string }> =>
  ws.request("sessions.consultSend", { id, text });
export const closeConsult = (ws: WsClient, id: string) => ws.request("sessions.consultClose", { id });
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
  head: string | null; base: string | null; headSha?: string | null;
  review: "approved" | "changes" | "review" | null;
  stack: { id: string; position: number; size: number; native?: boolean; inNative?: boolean } | null;
  reviewers?: { login: string; state: "requested" | "approved" | "changes" }[];
  ci?: "success" | "failure" | "pending" | null; conflict?: boolean;
  ciRunning?: boolean;                      // el CI falló pero quedan checks corriendo
  behind?: boolean;                         // atrasada respecto de su base
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
  mergeAll?: Record<string, MergeAllJob>;   // clave del desarrollo -> «Mergear todo»
  closed?: GhPr[];                      // PRs de desarrollos con sesión que ya se cerraron/mergearon
  // última resincronización completa de PRs (ok = se aceptó; si no, GitHub respondió raro y no se borró nada)
  sync?: { at: string; nodes: number; issueCount: number; cached: number; gone: number; ok: boolean } | null;
}
export const fetchGithubReviews = (ws: WsClient): Promise<GithubReviews> => ws.request("reviews.github", {});
/** "Revisar stack": una sesión para varias PRs pendientes de un stack (archiva las individuales). */
export const startStackReview = (ws: WsClient, urls: string[]): Promise<{ id: string; created: boolean; process: Process }> =>
  ws.request("reviews.startStack", { urls });
/** «Revisar de nuevo» una revisión de varias PRs (stack): re-review de esas PRs en su sesión. */
export const restartReview = (ws: WsClient, id: string, urls: string[]): Promise<{ id: string; created: boolean; process: Process }> =>
  ws.request("reviews.restart", { id, urls });
export const startReview = (ws: WsClient, url: string): Promise<{ id: string; created: boolean; process: Process }> =>
  ws.request("reviews.start", { url });
export interface MergeJob {
  state: "rebasing" | "waiting" | "waiting_ci" | "merging" | "restacking" | "done" | "error";
  error: string | null; restacked: string[] | null;
  repo?: string; number?: number; title?: string; above?: { url: string }[];
  native?: boolean; merged_at?: string | null; url?: string;
}
/** Las PRs abiertas de la org (sin las tuyas), por repo: para elegir cuál revisar. */
export interface OpenPr { url: string; number: number; title: string | null; author: string | null; draft: boolean }
export const fetchOpenPrs = (ws: WsClient): Promise<{ repos: Record<string, OpenPr[]> }> => ws.request("reviews.openPrs", {});
export const mergePr = (ws: WsClient, url: string): Promise<MergeJob> => ws.request("reviews.merge", { url });
/** «Mergear todo» de un desarrollo: running (avanzando), error (detenido por un problema), stopped (lo
 *  detuviste), done. `waiting`: por qué alguna PR todavía no se mergea. */
export interface MergeAllJob { state: "running" | "error" | "stopped" | "done"; total: number; done: number;
  error: string | null; current: string[]; waiting: string | null; at: string }
export const mergeAll = (ws: WsClient, key: string, urls: string[]): Promise<MergeAllJob> => ws.request("dev.mergeAll", { key, urls });
export const mergeAllResume = (ws: WsClient, key: string): Promise<{ ok: boolean }> => ws.request("dev.mergeAllResume", { key });
export const mergeAllStop = (ws: WsClient, key: string): Promise<{ ok: boolean }> => ws.request("dev.mergeAllStop", { key });
export const mergeAllDismiss = (ws: WsClient, key: string): Promise<{ ok: boolean }> => ws.request("dev.mergeAllDismiss", { key });
export const dismissMerge = (ws: WsClient, url: string) => ws.request("reviews.mergeDismiss", { url });
/** Desarmar el auto-merge armado desde el IDE (lo quita en GitHub). */
export const cancelMerge = (ws: WsClient, url: string): Promise<{ ok: boolean }> => ws.request("reviews.mergeCancel", { url });
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

/** Detalle de una sesión para la lista de la barra inferior: por qué te espera (último mensaje, el permiso o la
 *  pregunta con opciones que tiene abiertos) o qué está haciendo (lo último que hizo). */
export interface AttentionQuestion {
  question: string | null; header: string | null; multiSelect: boolean;
  options: { label: string | null; description: string | null }[];
}
export interface Attention {
  id: string; process: string;
  activity: { state?: string; since?: string; note?: string | null; reason?: string | null };
  message: string | null; messageAt: string | null;
  pending: { id: string; tool: string; summary: string; at: string; command?: string; description?: string | null;
    questions?: AttentionQuestion[] } | null;
  recent: { tool: string; summary: string; at: string }[];
}
export const fetchAttention = (ws: WsClient, id: string): Promise<Attention> => ws.request("sessions.attention", { id });
/** `since` y `pending`: lo que el usuario está viendo (si la sesión cambió de pregunta, el server lo rechaza). */
export const replyAttention = (ws: WsClient, p: {
  id: string; action: "text" | "approve" | "deny" | "answer"; text?: string; answers?: Record<string, string>;
  since?: string; pending?: string | null;
}): Promise<{ ok: boolean; done: string }> => ws.request("sessions.attentionReply", p);

/** Registro de herramientas evaluadas (lo lleva la sesión Plugins con `ide tools`). */
export interface ToolEntry { name: string; link: string | null; state: string; reason: string | null; created: string; updated: string }
export interface ToolHistory { at: string; from: string | null; to: string; reason: string | null; actor: string | null }
export const fetchTools = (ws: WsClient, q?: string, state?: string): Promise<{ tools: ToolEntry[]; states: string[] }> =>
  ws.request("tools.list", { q: q || null, state: state || null });
export const fetchTool = (ws: WsClient, name: string): Promise<{ tool: ToolEntry; history: ToolHistory[] }> =>
  ws.request("tools.show", { name });

/** Una tarjeta de Notion como Markdown (tab «Notion» del IDE). */
export const fetchNotionPage = (ws: WsClient, url: string): Promise<{ url: string; title: string | null; status: string | null; markdown: string; notionUrl?: string }> =>
  ws.request("dev.notionPage", { url });
/** El interruptor del módulo Notion: el subticket se muestra (o no) en la card. */
export const setSubTicketCard = (ws: WsClient, id: string, url: string, show: boolean): Promise<{ ok: boolean }> =>
  ws.request("dev.ticketSubCard", { id, url, show });

/** Sube un archivo a `attachments/` de la sesión por HTTP (crudo, hasta 1 GB): por el websocket un archivo grande
 *  cortaba la conexión y la UI lo veía como una caída del server. */
export async function uploadAttachment(id: string, file: File, dir = ""): Promise<{ path: string; name: string; size: number }> {
  const q = new URLSearchParams({ name: file.name || "archivo", ...(dir ? { dir } : {}) });
  const r = await fetch(`/api/sessions/${encodeURIComponent(id)}/attachments/upload?${q}`, { method: "POST", body: file });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error(data?.message ?? `no se pudo subir ${file.name} (${r.status})`);
  return data;
}
