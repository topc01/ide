// ui/src/modules/sessions/activity.ts
/** Actividad del claude de una sesión, otra dimensión que el estado del desarrollo: trabajando,
 *  esperando tu input (por los hooks de claude) o stale (el claude no corre y el desarrollo sigue
 *  activo). Se ve en el punto junto al título de la card. */
import type { FolderSession } from "../../transport/folderSessions";
import type { DevStateInfo } from "./devStates";

export type Activity = "working" | "waiting" | "outdated" | "stale" | "queued" | "running" | "idle" | "frozen" | "paused";

/** `done`: el desarrollo no sigue activo (mergeado, pausado, revisión publicada): parado no es stale. */
export function activityOf(s: FolderSession, dev?: DevStateInfo | null): Activity {
  if (s.process === "queued") return "queued";
  if (s.process === "running" && s.frozen) return "frozen";
  if (s.process === "running") return s.activity?.state ?? "running";
  if (s.paused) return "paused";
  const done = s.kind === "main" || s.kind === "ide" || s.kind === "recursos" || s.kind === "plugins"
    || (s.kind === "review" ? ["approved", "changes-requested"].includes(s.status ?? "") || ["merged", "closed"].includes(s.prState ?? "")
      : !!dev && (dev.state === "merged" || dev.state === "paused"));
  return done ? "idle" : "stale";
}

/** La hora (HH:MM, local) en que claude terminó el turno, si te espera. */
export const waitTime = (s?: FolderSession) => (s?.activity?.state === "waiting" || s?.activity?.state === "outdated") && s.activity.since
  && s.activity.reason !== "launch"     // recién lanzada: no terminó ningún turno
  ? new Date(s.activity.since).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" }) : null;

export const isWaiting = (s?: FolderSession) => !!s && s.process === "running" && s.activity?.state === "waiting";

/** [símbolo, clase, explicación]. */
export const ACTIVITY: Record<Activity, [string, string, string]> = {
  // trabajando gira y es de otro color: no se confunde con el punto fijo de "espera tu input"
  working: ["◐", "inline-block leading-none text-sky-400 animate-spin", "claude está trabajando"],
  waiting: ["●", "text-orange-500", "claude terminó: espera tu input"],
  // te esperaba, pero después pasó algo en sus PRs: no cuenta en «te esperan»
  outdated: ["●", "text-muted-foreground", "te esperaba, pero después pasó algo en sus PRs: probablemente ya no te espera"],
  // sin relleno: lo que no es "trabaja" ni "te espera" (no se sabe todavía, o no está corriendo)
  running: ["◯", "text-primary", "claude corriendo (todavía no se sabe si trabaja o te espera)"],
  queued: ["◌", "text-muted-foreground", "en cola (max_running)"],
  stale: ["◯", "text-red-500", "stale: el claude no está corriendo y el desarrollo sigue activo (se abre al entrar a la sesión)"],
  idle: ["○", "text-muted-foreground", "claude parado"],
  frozen: ["⏸", "text-violet-400", "congelada: su claude está detenido donde estaba (sin gastar CPU ni tokens; la memoria sigue ocupada)"],
  paused: ["⏸", "text-muted-foreground", "pausada: su claude está cerrado (sin memoria ni tokens); Reanudar en las acciones de la card"],
};

/** Las que te esperan, primero (orden estable). */
export function waitingFirst<T extends { session?: FolderSession }>(xs: T[]): T[] {
  return [...xs.filter((x) => isWaiting(x.session)), ...xs.filter((x) => !isWaiting(x.session))];
}
