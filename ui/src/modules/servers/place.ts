// ui/src/modules/servers/place.ts
import { useCurrentDev, type Dev } from "../../main/currentDev";
import { prPlace, useRuns, type Run, type RunsState } from "../../transport/runs";
import type { GhPr } from "../../transport/folderSessions";
import { byRepoStack } from "../sessions/desarrollos";

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

/** Un bloque del módulo Servidores: un stack de un repo (o el worktree de la sesión sin PR) y dónde se
 *  levanta. Un stack corre desde la rama de su PR de más arriba (contiene a las de abajo). */
export interface ServerBlock {
  key: string; repo: string;
  prs: GhPr[];                  // el stack, de abajo hacia arriba ([] = rama de la sesión sin PR)
  place: string;                // id de la sesión o `wt-<repo>-<n>` (worktree aparte)
  where: "session" | "pr";
  exists: boolean;              // el worktree ya está (los aparte se crean al dar ▶)
  branch: string | null;        // la rama (o @sha) en la que está / estará
  top?: GhPr;                   // la PR de más arriba (para crear su worktree)
}

export function devBlocks(dev: Dev | null, runs: RunsState | null): ServerBlock[] {
  if (!dev) return [];
  const sessionRepos = (dev.session?.repos ?? []).filter((r) => r.state === "ok");
  const out: ServerBlock[] = [];
  const covered = new Set<string>();
  for (const g of byRepoStack(dev.prs)) {
    for (const stack of g.stacks) {
      const top = stack[stack.length - 1];
      const heads = stack.map((p) => p.head);
      const wt = sessionRepos.find((r) => r.name === g.repo && r.branch && heads.includes(r.branch));
      if (wt && dev.session) {
        covered.add(g.repo);
        out.push({ key: `${g.repo}:${top.url}`, repo: g.repo, prs: stack, place: dev.session.id, where: "session",
                   exists: true, branch: wt.branch ?? null, top });
      } else {
        const place = prPlace(g.repo, top.number);
        const found = runs?.places.find((p) => p.id === place);
        out.push({ key: `${g.repo}:${top.url}`, repo: g.repo, prs: stack, place, where: "pr",
                   exists: !!found?.repos.includes(g.repo), branch: found?.heads?.[g.repo] ?? top.head, top });
      }
    }
  }
  // repos de la sesión cuya rama no tiene PR (o no está en ningún stack de arriba)
  for (const r of sessionRepos) {
    if (covered.has(r.name) || !dev.session) continue;
    out.push({ key: `${r.name}:session`, repo: r.name, prs: [], place: dev.session.id, where: "session",
               exists: true, branch: r.branch ?? null });
  }
  return out.sort((a, b) => a.repo.localeCompare(b.repo) || Number(b.where === "session") - Number(a.where === "session"));
}

/** El puerto de una api corriendo (su `run` con URL). */
export const runPort = (r?: Run) => {
  const u = r?.urls?.[0];
  const m = u?.match(/:(\d+)(?:\/|$)/);
  return m ? Number(m[1]) : null;
};
