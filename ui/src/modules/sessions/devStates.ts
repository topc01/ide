// ui/src/modules/sessions/devStates.ts
/** Estado del DESARROLLO (otra dimensión que el de la PR): qué toca o qué lo frena. Solo local.
 *  Después de "listo para revisión" manda la PR (revisión, cambios, aprobada, merge). */
import { createContext, useContext } from "react";
import type { GhPr } from "../../transport/folderSessions";
import { devKeys } from "./desarrollos";

export type DevState = "investigating" | "ready-to-develop" | "developing" | "ready-for-review"
  | "waiting-input" | "questions" | "blocked-definitions" | "blocked-client" | "blocked-dev" | "paused";

/** [nombre, fondo de la card, color del texto]. Los bloqueos, fuertes; lo que avanza, suave. */
export const DEV_STATE: Record<DevState, [string, string, string]> = {
  "waiting-input": ["esperando tu input", "bg-orange-500/[0.18]", "text-orange-300"],
  questions: ["dudas", "bg-amber-400/[0.15]", "text-amber-300"],
  "blocked-definitions": ["bloqueado por definiciones", "bg-rose-500/[0.14]", "text-rose-300"],
  "blocked-client": ["bloqueado por el cliente", "bg-red-500/[0.16]", "text-red-400"],
  "blocked-dev": ["bloqueado por otro desarrollo", "bg-fuchsia-500/[0.12]", "text-fuchsia-300"],
  investigating: ["investigando", "bg-sky-500/[0.07]", "text-sky-300"],
  "ready-to-develop": ["listo para desarrollar", "bg-indigo-400/[0.08]", "text-indigo-300"],
  developing: ["desarrollando", "bg-emerald-500/[0.07]", "text-emerald-300"],
  "ready-for-review": ["listo para revisión", "bg-teal-400/[0.12]", "text-teal-300"],
  paused: ["pausado", "bg-zinc-500/[0.10]", "text-muted-foreground"],
};
/** Orden de los grupos: primero lo que hay que destrabar. */
export const DEV_STATE_ORDER: DevState[] = ["waiting-input", "questions", "blocked-definitions", "blocked-client",
  "blocked-dev", "investigating", "ready-to-develop", "developing", "ready-for-review", "paused"];
export const BLOCKED: DevState[] = ["waiting-input", "questions", "blocked-definitions", "blocked-client", "blocked-dev"];
const ACTIVE: DevState[] = ["investigating", "ready-to-develop", "developing", ...BLOCKED];

export interface DevStateInfo { status: DevState; note: string | null; since: string | null; inferred: boolean }
export type DevStates = Record<string, { status: string; note?: string | null; since?: string | null }>;

/** El estado del desarrollo: el puesto (por clave, o heredado de su stack/PRs) o, si no hay, uno
 *  inferido de sus PRs (draft = desarrollando; lista para revisión = listo para revisión). */
export function devStateOf(states: DevStates | undefined, key: string, prs: GhPr[] = []): DevStateInfo | null {
  for (const k of devKeys(key, prs)) {
    const s = states?.[k];
    if (s && s.status in DEV_STATE) return { status: s.status as DevState, note: s.note ?? null, since: s.since ?? null, inferred: false };
  }
  if (!prs.length) return null;
  return { status: prs.some((p) => p.draft) ? "developing" : "ready-for-review", note: null, since: null, inferred: true };
}

/** El desarrollo sigue activo pero alguna PR ya no está en draft (debería estar en draft hasta terminar). */
export const outOfDraft = (st: DevStateInfo | null, prs: GhPr[]) =>
  !!st && !st.inferred && ACTIVE.includes(st.status) && prs.some((p) => !p.draft);

/** Con qué dimensión se colorean las cards de una sección (la que agrupa, o la elegida en Configuración). */
export type ColorBy = "pr" | "dev";
export const CardColor = createContext<ColorBy>("pr");
export const useCardColor = () => useContext(CardColor);

export const ago = (iso: string | null) => {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? "recién" : s < 3600 ? `${Math.round(s / 60)} min` : s < 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`;
};
