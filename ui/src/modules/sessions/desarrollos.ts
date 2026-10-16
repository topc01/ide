// ui/src/modules/sessions/desarrollos.ts
/** Modelo "desarrollo" de Mis desarrollos (spec 2026-10-16-desarrollos, P1). Una rama/PR pertenece
 *  a un solo desarrollo, en este orden: (1) la sesión cuyos worktrees están en esa rama (y el resto
 *  de su stack), (2) un stack tuyo sin sesión, (3) una PR suelta. Las sesiones sin PR también son
 *  desarrollos. */
import type { FolderSession, GhPr, GithubReviews, MergeJob } from "../../transport/folderSessions";

export type MineStatus = "returned" | "waiting" | "missing" | "draft" | "approved";

export interface Desarrollo {
  key: string;
  session?: FolderSession;
  prs: GhPr[];                      // de abajo hacia arriba (la primera es la próxima a mergear)
  status: MineStatus | "nopr" | "merges";
  job?: MergeJob;                   // merge de una PR que ya no está abierta (grupo Merges)
}

const byPosition = (a: GhPr, b: GhPr) => (a.stack?.position ?? 0) - (b.stack?.position ?? 0);

export function deriveMine(tickets: FolderSession[], gh: GithubReviews | null): Desarrollo[] {
  const bucket = new Map<string, MineStatus>();
  const mine: GhPr[] = [];
  for (const [k, list] of Object.entries(gh?.mine ?? {}) as [MineStatus, GhPr[]][]) {
    for (const pr of list ?? []) { bucket.set(pr.url, k); mine.push(pr); }
  }
  const taken = new Set<string>();
  const stackOf = (pr: GhPr) => pr.stack ? mine.filter((p) => p.stack?.id === pr.stack!.id) : [pr];
  const out: Desarrollo[] = [];
  const status = (prs: GhPr[]): Desarrollo["status"] => prs.length ? bucket.get(prs[0].url) ?? "missing" : "nopr";

  // (1) sesiones de ticket: las PRs de las ramas de sus worktrees, con su stack completo
  for (const s of tickets) {
    const own = mine.filter((p) => !taken.has(p.url)
      && s.repos.some((r) => r.branch && r.name === p.repo && r.branch === p.head));
    const prs = [...new Set(own.flatMap(stackOf))].filter((p) => !taken.has(p.url)).sort(byPosition);
    prs.forEach((p) => taken.add(p.url));
    out.push({ key: `s:${s.id}`, session: s, prs, status: status(prs) });
  }
  // (2) stacks sin sesión y (3) PRs sueltas
  for (const pr of mine) {
    if (taken.has(pr.url)) continue;
    const prs = stackOf(pr).filter((p) => !taken.has(p.url)).sort(byPosition);
    prs.forEach((p) => taken.add(p.url));
    out.push({ key: prs.length > 1 ? `st:${pr.stack!.id}` : `p:${pr.url}`, prs, status: status(prs) });
  }
  // merges cuya PR ya no está abierta (GitHub la mergeó): siguen visibles (moradas 24 h)
  const recent = (j: MergeJob) => j.state !== "done" || (!!j.merged_at && Date.now() - Date.parse(j.merged_at) < 864e5);
  for (const [url, job] of Object.entries(gh?.merges ?? {})) {
    if (bucket.has(url) || !recent(job)) continue;
    const pr: GhPr = { url, title: job.title ?? url, number: job.number ?? 0, repo: job.repo ?? "", author: "",
      draft: false, updatedAt: null, sessionId: "", head: null, base: null, review: null, stack: null };
    out.push({ key: `m:${url}`, prs: [pr], status: "merges", job });
  }
  return out;
}
