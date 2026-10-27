// ui/src/modules/sessions/devStates.ts
/** Estado del desarrollo, uno solo: una FASE que avanza (con PRs fuera de draft, o en draft con revisores
 *  pedidos o revisión, la da GitHub con la peor de sus PRs) y, encima, un BLOQUEO opcional (con nota) que la tapa sin borrarla. Cualquier fase
 *  se puede poner a mano: la puesta desde la UI gana hasta que la fase de GitHub cambie. Solo local
 *  (base del IDE). */
import type { GhPr, MergeJob } from "../../transport/folderSessions";
import { devKeys } from "./desarrollos";

export type Phase = "investigating" | "developing" | "ready-for-review" | "testing" | "in-review"
  | "changes-requested" | "approved" | "merging" | "merged";
export type Block = "waiting-input" | "blocked" | "paused";
export type State = Phase | Block;

/** [nombre, fondo de la card, color del texto, qué significa]. Bloqueos fuertes; fases suaves. */
export const STATE: Record<State, [string, string, string, string]> = {
  "waiting-input": ["esperando tu input", "bg-orange-500/[0.18]", "text-orange-300", "la sesión te preguntó algo o necesita un OK tuyo"],
  blocked: ["bloqueado", "bg-red-500/[0.15]", "text-red-400", "no se puede avanzar: la nota dice por qué o de quién depende"],
  paused: ["pausado", "bg-zinc-500/[0.10]", "text-muted-foreground", "en espera, sin apuro"],
  investigating: ["investigando", "bg-slate-400/[0.08]", "text-slate-300", "entendiendo el problema, todavía sin código"],
  developing: ["desarrollando", "bg-violet-400/[0.09]", "text-violet-300", "implementando (las PRs en draft)"],
  "ready-for-review": ["listo para revisión", "bg-teal-400/[0.12]", "text-teal-300", "terminado; falta sacar las PRs de draft"],
  testing: ["en testeo", "bg-cyan-400/[0.08]", "text-cyan-300", "PRs fuera de draft, probándose antes de pedir revisores"],
  "in-review": ["en revisión", "bg-sky-500/[0.08]", "text-sky-300", "con revisores pedidos"],
  "changes-requested": ["cambios pedidos", "bg-amber-400/[0.09]", "text-amber-300", "un revisor pidió cambios"],
  approved: ["aprobado", "bg-emerald-500/[0.08]", "text-emerald-300", "aprobado, listo para mergear"],
  merging: ["mergeando", "bg-purple-500/[0.09]", "text-purple-300", "el IDE lo está mergeando"],
  merged: ["mergeado", "bg-purple-500/[0.09]", "text-purple-300", "todas sus PRs ya están mergeadas"],
};
/** Orden de los grupos: lo que hay que destrabar primero, después el flujo, pausado al final. */
export const STATE_ORDER: State[] = ["waiting-input", "blocked", "changes-requested", "investigating", "developing",
  "ready-for-review", "testing", "in-review", "approved", "merging", "merged", "paused"];
export const BLOCKS: Block[] = ["waiting-input", "blocked", "paused"];
/** Las pausas que se ponen: "esperando tu input" ya no es del desarrollo (es la actividad de la
 *  sesión, por los hooks); las que quedaron puestas se ven hasta que las cambies. */
export const PICK_BLOCKS: Block[] = ["blocked", "paused"];
/** Las fases que se pueden poner a mano (todas menos "mergeando", que solo la da el merge). */
export const PHASES: Phase[] = ["investigating", "developing", "ready-for-review", "testing", "in-review",
  "changes-requested", "approved", "merged"];
const PRE_GITHUB: Phase[] = ["investigating", "developing", "ready-for-review"];

export interface DevStateInfo {
  state: State;                 // lo que se muestra/agrupa: el bloqueo si hay, si no la fase
  phase: Phase; block: Block | null;
  manual: Phase | null;         // la fase puesta a mano (puede quedar tapada por la de GitHub)
  github: boolean;              // la fase sale de sus PRs (fuera de draft, mergeando o mergeadas)
  gh: Phase | null;             // la fase según GitHub (se manda al ponerla a mano)
  note: string | null; since: string | null;
  actor: string | null;         // quién lo puso: "ide" (tú, desde la UI), "claude:<sesión>", "github"…
  inferred: boolean;            // no hay nada puesto: fase deducida
  outOfDraft: boolean;          // puesta a mano como activa, pero alguna PR ya salió de draft
}
export type DevStates = Record<string, { phase?: string | null; block?: string | null; note?: string | null;
  since?: string | null; gh?: string | null; actor?: string | null }>;
const MERGE_ACTIVE = ["rebasing", "waiting", "waiting_ci", "merging", "restacking"];

/** Fase según GitHub (la peor de las PRs abiertas que cuentan; mergeado si todas lo están), o null. Cuentan
 *  las fuera de draft y las en draft que ya tienen revisores pedidos o revisión: en el equipo se revisa en
 *  draft (CI corre después de aprobar). Un draft sin revisores todavía se está trabajando. */
export function githubPhase(prs: GhPr[], job?: MergeJob, merged: GhPr[] = []): Phase | null {
  if (job && MERGE_ACTIVE.includes(job.state)) return "merging";
  if (job?.state === "done") return "merged";
  if (!prs.length) return merged.length ? "merged" : null;
  const open = prs.filter((p) => !p.draft || p.review || p.reviewers?.length);
  if (!open.length) return null;
  if (open.some((p) => p.review === "changes")) return "changes-requested";
  if (open.some((p) => !p.review && !p.reviewers?.length)) return "testing";
  if (open.some((p) => p.review !== "approved")) return "in-review";
  return "approved";
}

export function devStateOf(states: DevStates | undefined, key: string, prs: GhPr[] = [], job?: MergeJob,
  merged: GhPr[] = []): DevStateInfo {
  const s = devKeys(key, prs).map((k) => states?.[k]).find(Boolean);
  const manual = (PHASES as string[]).includes(s?.phase ?? "") ? s!.phase as Phase : null;
  const block = (BLOCKS as string[]).includes(s?.block ?? "") ? s!.block as Block : null;
  const gh = githubPhase(prs, job, merged);
  // puesta a mano desde la UI: gana mientras GitHub siga en la fase de ese momento
  const pinned = !!manual && !!s && "gh" in s && (s.gh ?? null) === gh;
  // "investigando" puesto por la sesión queda viejo apenas abre una PR: con PRs es "desarrollando"
  // (salvo que el usuario lo haya fijado a mano)
  const stale = manual === "investigating" && prs.length > 0 && !pinned;
  const phase: Phase = (pinned ? manual : gh ?? (stale ? null : manual)) ?? (prs.length ? "developing" : "investigating");
  return {
    state: block ?? phase, phase, block, manual, github: !!gh && !pinned, gh, note: s?.note ?? null, since: s?.since ?? null, actor: s?.actor ?? null,
    inferred: !gh && !manual, outOfDraft: !!gh && !pinned && !!manual && prs.some((p) => !p.draft) && PRE_GITHUB.includes(manual) && manual !== "ready-for-review"
      && gh !== "merging" && gh !== "merged",
  };
}

export const ago = (iso: string | null) => {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? "segundos" : s < 3600 ? `${Math.round(s / 60)} min` : s < 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`;
};
