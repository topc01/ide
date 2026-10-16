// ui/src/modules/servers/place.ts
import { useCurrentDev, type Dev } from "../../main/currentDev";
import { prPlace, useRuns, type RunsState } from "../../transport/runs";
import type { GhPr } from "../../transport/folderSessions";

/** Dónde corre/edita el desarrollo actual: los worktrees de su sesión, o el de su PR (sin sesión). */
export interface DevPlace {
  place: string; repos: string[]; exists: boolean;
  pr?: GhPr;                    // sin sesión: la PR (la de más arriba del stack: contiene a todas)
}

export function devPlace(dev: Dev | null, runs: RunsState | null): DevPlace | null {
  if (!dev) return null;
  if (dev.session) {
    return { place: dev.session.id, exists: true,
             repos: dev.session.repos.filter((r) => r.state === "ok").map((r) => r.name) };
  }
  const pr = dev.prs[dev.prs.length - 1];
  if (!pr) return null;
  const place = prPlace(pr.repo, pr.number);
  const found = runs?.places.find((p) => p.id === place);
  return { place, pr, exists: !!found, repos: found?.repos ?? [pr.repo] };
}

export function useDevPlace() {
  const dev = useCurrentDev();
  const { state, error } = useRuns();
  return { dev, runs: state, error, place: devPlace(dev, state) };
}
