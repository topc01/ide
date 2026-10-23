// ui/src/modules/sessions/activity.ts
/** Actividad del claude de una sesión, otra dimensión que el estado del desarrollo: trabajando,
 *  esperando tu input (por los hooks de claude) o stale (el claude no corre y el desarrollo sigue
 *  activo). Se ve en el punto junto al título de la card. */
import type { FolderSession } from "../../transport/folderSessions";
import type { DevStateInfo } from "./devStates";

export type Activity = "working" | "waiting" | "stale" | "queued" | "running" | "idle";

/** `done`: el desarrollo no sigue activo (mergeado, pausado, revisión publicada): parado no es stale. */
export function activityOf(s: FolderSession, dev?: DevStateInfo | null): Activity {
  if (s.process === "queued") return "queued";
  if (s.process === "running") return s.activity?.state ?? "running";
  const done = s.kind === "main" || s.kind === "ide"
    || (s.kind === "review" ? ["approved", "changes-requested"].includes(s.status ?? "") || ["merged", "closed"].includes(s.prState ?? "")
      : !!dev && (dev.state === "merged" || dev.state === "paused"));
  return done ? "idle" : "stale";
}

export const isWaiting = (s?: FolderSession) => !!s && s.process === "running" && s.activity?.state === "waiting";

/** [símbolo, clase, explicación]. */
export const ACTIVITY: Record<Activity, [string, string, string]> = {
  working: ["●", "text-amber-300 animate-pulse", "claude está trabajando"],
  waiting: ["●", "text-orange-500", "claude terminó: espera tu input"],
  running: ["●", "text-primary", "claude corriendo"],
  queued: ["◌", "text-muted-foreground", "en cola (max_running)"],
  stale: ["●", "text-red-500", "stale: el claude no está corriendo y el desarrollo sigue activo"],
  idle: ["○", "text-muted-foreground", "claude parado"],
};

/** Las que te esperan, primero (orden estable). */
export function waitingFirst<T extends { session?: FolderSession }>(xs: T[]): T[] {
  return [...xs.filter((x) => isWaiting(x.session)), ...xs.filter((x) => !isWaiting(x.session))];
}
