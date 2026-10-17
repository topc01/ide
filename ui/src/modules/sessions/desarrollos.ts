// ui/src/modules/sessions/desarrollos.ts
/** Modelo "desarrollo" de Mis desarrollos (spec 2026-10-16-desarrollos, P1). Una rama/PR pertenece
 *  a un solo desarrollo, en este orden: (1) la sesión cuyos worktrees están en esa rama (y el resto
 *  de su stack), (2) un stack tuyo sin sesión, (3) una PR suelta. Las sesiones sin PR también son
 *  desarrollos. */
import type { FolderSession, GhPr, GithubReviews, MergeJob, PrLinks } from "../../transport/folderSessions";

export type MineStatus = "returned" | "waiting" | "missing" | "draft" | "approved";

export interface Desarrollo {
  key: string;
  session?: FolderSession;
  prs: GhPr[];                      // de abajo hacia arriba (la primera es la próxima a mergear)
  status: MineStatus | "nopr" | "merges";
  job?: MergeJob;                   // merge de una PR que ya no está abierta (grupo Merges)
}

const byPosition = (a: GhPr, b: GhPr) => (a.stack?.position ?? 0) - (b.stack?.position ?? 0);

/** Las PRs de un desarrollo por repo y, dentro, por stack (cada stack de abajo hacia arriba). Un
 *  desarrollo fullstack tiene un grupo por repo; la de abajo de cada stack es la que se mergea. */
export function byRepoStack(prs: GhPr[]): { repo: string; stacks: GhPr[][] }[] {
  const repos = new Map<string, Map<string, GhPr[]>>();
  for (const p of prs) {
    const r = repos.get(p.repo) ?? new Map<string, GhPr[]>();
    repos.set(p.repo, r);
    const k = p.stack?.id ?? p.url;
    r.set(k, [...(r.get(k) ?? []), p]);
  }
  return [...repos.entries()].sort(([a], [b]) => a.localeCompare(b))
    .map(([repo, st]) => ({ repo, stacks: [...st.values()].map((l) => l.sort(byPosition)) }));
}

/** Orden de prioridad para agrupar un desarrollo con varias PRs: manda la peor. */
const WORST: MineStatus[] = ["returned", "missing", "waiting", "draft", "approved"];
export function worstStatus(prs: GhPr[], bucket: Map<string, MineStatus>): MineStatus {
  const st = prs.map((p) => bucket.get(p.url) ?? "missing");
  return WORST.find((w) => st.includes(w)) ?? "missing";
}

/** La PR que da el tono de la card (review) y la del CI: la peor de cada cosa. */
const REVIEW_RANK: Record<string, number> = { "changes-requested": 0, changes: 0, reviewing: 1, review: 1, approved: 3 };
export function worstPr(prs: GhPr[]): { review?: GhPr; ci?: GhPr } {
  const rv = (p: GhPr) => p.review ? REVIEW_RANK[p.review] ?? 2 : 2;
  const ci = (p: GhPr) => ({ failure: 0, pending: 1, success: 2 } as Record<string, number>)[p.ci ?? ""] ?? 3;
  return { review: [...prs].sort((a, b) => rv(a) - rv(b))[0], ci: [...prs].sort((a, b) => ci(a) - ci(b))[0] };
}

/** Claves con las que se pudo marcar un desarrollo: la suya y, si cambió de clave (una PR que ahora
 *  tiene sesión), las de su stack y sus PRs. */
export function devKeys(key: string, prs: GhPr[] = []): string[] {
  return [key, ...prs.flatMap((p) => [...(p.stack ? [`st:${p.stack.id}`] : []), `p:${p.url}`])];
}
/** Número del desarrollo (#12): el de su clave o, si cambió de clave, el de su stack/PRs. */
export function devIndexOf(index: Record<string, number> | undefined, key: string, prs: GhPr[] = []): number | null {
  if (!index) return null;
  for (const k of devKeys(key, prs)) if (index[k] !== undefined) return index[k];
  return null;
}
/** ¿Está oculto? (marcado con su clave o con la de su stack/PRs). */
export function isHidden(hidden: string[] | undefined, key: string, prs: GhPr[] = []): string | null {
  if (!hidden?.length) return null;
  return devKeys(key, prs).find((k) => hidden.includes(k)) ?? null;
}

/** Nombre puesto en el IDE; si el desarrollo cambió de clave (la PR ahora tiene sesión), el de su stack o PRs. */
export function devName(names: Record<string, string> | undefined, key: string, prs: GhPr[] = []): string | null {
  if (!names) return null;
  if (names[key]) return names[key];
  for (const p of prs) {
    const n = (p.stack && names[`st:${p.stack.id}`]) || names[`p:${p.url}`];
    if (n) return n;
  }
  return null;
}

/** `links`: PRs vinculadas a una sesión (pegajoso): siguen en su desarrollo aunque el worktree cambie
 *  de rama; con `out` se sacaron a mano y no vuelven por rama. */
export function deriveMine(tickets: FolderSession[], gh: GithubReviews | null, links: PrLinks = {}): Desarrollo[] {
  const bucket = new Map<string, MineStatus>();
  const mine: GhPr[] = [];
  for (const [k, list] of Object.entries(gh?.mine ?? {}) as [MineStatus, GhPr[]][]) {
    for (const pr of list ?? []) { bucket.set(pr.url, k); mine.push(pr); }
  }
  const taken = new Set<string>();
  const stackOf = (pr: GhPr) => pr.stack ? mine.filter((p) => p.stack?.id === pr.stack!.id) : [pr];
  const out: Desarrollo[] = [];
  const status = (prs: GhPr[]): Desarrollo["status"] => prs.length ? worstStatus(prs, bucket) : "nopr";

  // (1) sesiones de ticket: las PRs de las ramas de sus worktrees, con su stack completo
  for (const s of tickets) {
    const own = mine.filter((p) => {
      if (taken.has(p.url)) return false;
      const link = links[p.url];
      if (link) return link.sid === s.id && !link.out;
      return s.repos.some((r) => r.branch && r.name === p.repo && r.branch === p.head);
    });
    const prs = byRepoStack([...new Set(own.flatMap(stackOf))].filter((p) => !taken.has(p.url)))
      .flatMap((g) => g.stacks.flat());
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
