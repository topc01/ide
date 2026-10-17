// ui/src/modules/sessions/devStates.ts
/** Estado del desarrollo, uno solo: una FASE que avanza (a mano hasta "listo para revisión"; con PRs
 *  fuera de draft, la da GitHub con la peor de sus PRs) y, encima, un BLOQUEO opcional (con nota)
 *  que la tapa sin borrarla. Solo local (base del IDE). */
import type { GhPr, MergeJob } from "../../transport/folderSessions";
import { devKeys } from "./desarrollos";

export type Phase = "investigating" | "ready-to-develop" | "developing" | "ready-for-review"
  | "needs-reviewers" | "in-review" | "changes-requested" | "approved" | "merging" | "merged";
export type Block = "waiting-input" | "questions" | "blocked-definitions" | "blocked-client" | "blocked-dev" | "paused";
export type State = Phase | Block;

/** [nombre, fondo de la card, color del texto]. Bloqueos fuertes; fases suaves. */
export const STATE: Record<State, [string, string, string]> = {
  "waiting-input": ["esperando tu input", "bg-orange-500/[0.18]", "text-orange-300"],
  questions: ["dudas", "bg-yellow-400/[0.13]", "text-yellow-300"],
  "blocked-definitions": ["bloqueado por definiciones", "bg-rose-500/[0.14]", "text-rose-300"],
  "blocked-client": ["bloqueado por el cliente", "bg-red-500/[0.16]", "text-red-400"],
  "blocked-dev": ["bloqueado por otro desarrollo", "bg-fuchsia-500/[0.12]", "text-fuchsia-300"],
  paused: ["pausado", "bg-zinc-500/[0.10]", "text-muted-foreground"],
  investigating: ["investigando", "bg-slate-400/[0.08]", "text-slate-300"],
  "ready-to-develop": ["listo para desarrollar", "bg-indigo-400/[0.08]", "text-indigo-300"],
  developing: ["desarrollando", "bg-violet-400/[0.09]", "text-violet-300"],
  "ready-for-review": ["listo para revisión", "bg-teal-400/[0.12]", "text-teal-300"],
  "needs-reviewers": ["sin revisores", "bg-sky-500/[0.04]", "text-sky-300"],
  "in-review": ["en revisión", "bg-sky-500/[0.08]", "text-sky-300"],
  "changes-requested": ["cambios pedidos", "bg-amber-400/[0.09]", "text-amber-300"],
  approved: ["aprobada", "bg-emerald-500/[0.08]", "text-emerald-300"],
  merging: ["mergeando", "bg-purple-500/[0.09]", "text-purple-300"],
  merged: ["mergeada", "bg-purple-500/[0.09]", "text-purple-300"],
};
/** Orden de los grupos: lo que hay que destrabar primero, después el flujo, pausado al final. */
export const STATE_ORDER: State[] = ["waiting-input", "questions", "blocked-definitions", "blocked-client", "blocked-dev",
  "changes-requested", "investigating", "ready-to-develop", "developing", "ready-for-review", "needs-reviewers",
  "in-review", "approved", "merging", "merged", "paused"];
export const BLOCKS: Block[] = ["waiting-input", "questions", "blocked-definitions", "blocked-client", "blocked-dev", "paused"];
/** Las fases que se ponen a mano (después manda GitHub). */
export const MANUAL_PHASES: Phase[] = ["investigating", "ready-to-develop", "developing", "ready-for-review"];

export interface DevStateInfo {
  state: State;                 // lo que se muestra/agrupa: el bloqueo si hay, si no la fase
  phase: Phase; block: Block | null;
  manual: Phase | null;         // la fase puesta a mano (puede quedar tapada por la de GitHub)
  github: boolean;              // la fase sale de sus PRs (fuera de draft o mergeando)
  note: string | null; since: string | null;
  inferred: boolean;            // no hay nada puesto: fase deducida
  outOfDraft: boolean;          // puesta a mano como activa, pero alguna PR ya salió de draft
}
export type DevStates = Record<string, { phase?: string | null; block?: string | null; note?: string | null; since?: string | null }>;
const MERGE_ACTIVE = ["rebasing", "waiting", "waiting_ci", "merging", "restacking"];

/** Fase según GitHub (la peor de las PRs fuera de draft), o null si todas están en draft. */
function githubPhase(prs: GhPr[], job?: MergeJob): Phase | null {
  if (job && MERGE_ACTIVE.includes(job.state)) return "merging";
  if (job?.state === "done") return "merged";
  const open = prs.filter((p) => !p.draft);
  if (!open.length) return null;
  if (open.some((p) => p.review === "changes")) return "changes-requested";
  if (open.some((p) => !p.review && !p.reviewers?.length)) return "needs-reviewers";
  if (open.some((p) => p.review !== "approved")) return "in-review";
  return "approved";
}

export function devStateOf(states: DevStates | undefined, key: string, prs: GhPr[] = [], job?: MergeJob): DevStateInfo {
  const s = devKeys(key, prs).map((k) => states?.[k]).find(Boolean);
  const manual = (MANUAL_PHASES as string[]).includes(s?.phase ?? "") ? s!.phase as Phase : null;
  const block = (BLOCKS as string[]).includes(s?.block ?? "") ? s!.block as Block : null;
  const gh = githubPhase(prs, job);
  const phase: Phase = gh ?? manual ?? (prs.length ? "developing" : "investigating");
  return {
    state: block ?? phase, phase, block, manual, github: !!gh, note: s?.note ?? null, since: s?.since ?? null,
    inferred: !gh && !manual, outOfDraft: !!gh && !!manual && manual !== "ready-for-review" && gh !== "merging" && gh !== "merged",
  };
}

export const ago = (iso: string | null) => {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? "recién" : s < 3600 ? `${Math.round(s / 60)} min` : s < 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`;
};
