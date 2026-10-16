// ui/src/modules/github/GithubPanel.tsx
import { ExternalLink } from "lucide-react";
import { useFolders } from "../../state/folders";
import type { GhPr, GithubReviews } from "../../transport/folderSessions";
import { QueueItem, QueueItemAction, QueueItemActions, QueueList } from "../../components/ai-elements/queue";
import { CiMark, useGithubReviews } from "../sessions/ReviewsSection";
import { byRepoStack } from "../sessions/desarrollos";
import { useCurrentDev } from "../../main/currentDev";
import { desarrollos } from "../../layout/DevSelector";
import { cn } from "../../lib/utils";

const REVIEW = {
  approved: ["bg-emerald-500", "aprobada"],
  review: ["bg-sky-500", "en revisión"],
  changes: ["bg-amber-400", "pidieron cambios"],
} as const;

/** Las PRs del desarrollo actual (todas, aunque se haya elegido una de sus filas), por repo y stack. */
export function useDevPrs(): GhPr[] {
  const dev = useCurrentDev();
  return dev ? byRepoStack(dev.prs).flatMap((g) => g.stacks.flat()) : [];
}

/** Cabecera de repo antes de la primera PR de cada repo, si el desarrollo es fullstack. */
export function repoHeader(prs: GhPr[], i: number): string | null {
  const repos = new Set(prs.map((p) => p.repo));
  return repos.size > 1 && (i === 0 || prs[i - 1].repo !== prs[i].repo) ? prs[i].repo : null;
}

/** Los stacks completos (con PRs de otros) de las PRs del desarrollo; `own` = las del desarrollo. */
function devStacks(prs: GhPr[], gh: GithubReviews): { own: Set<string>; stacks: GhPr[][] } {
  const seen = new Set<string>();
  const stacks: GhPr[][] = [];
  for (const p of prs) {
    const key = p.stack?.id ?? p.url;
    if (seen.has(key)) continue;
    seen.add(key);
    stacks.push(p.stack ? gh.stacks?.[p.stack.id] ?? [p] : [p]);
  }
  return { own: new Set(prs.map((p) => p.url)), stacks };
}

/** `assigned`: la PR es tuya (autor) o figuras como revisor; si no, va tachada y atenuada. */
function StackItem({ pr, own, assigned, onOpen }:
  { pr: GhPr; own: boolean; assigned: boolean; onOpen?: () => void }) {
  const [color, label] = pr.review ? REVIEW[pr.review] : [null, "sin review"];
  return (
    <QueueItem className="min-w-0 px-1.5">
      <div onClick={onOpen} className={cn(onOpen && "cursor-pointer", "flex min-w-0 items-start gap-1.5 rounded border-l-2 border-transparent px-1.5 py-1 text-xs hover:bg-accent/60",
        own && "border-primary bg-accent", !assigned && "opacity-50")}>
        <span aria-label={label} title={label}
          className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", color ?? "border border-muted-foreground")} />
        <span className="mt-px font-mono text-[10px] text-muted-foreground">{pr.stack?.position ?? 1}</span>
        <div className="min-w-0 flex-1">
          <div className={cn("truncate", !assigned && "line-through")}
            title={assigned ? pr.title : `${pr.title} (no asignada a ti)`}>{pr.title}</div>
          <div className="truncate font-mono text-[10px] text-muted-foreground" title={`${pr.repo}#${pr.number} · ${pr.author}`}>{pr.repo}#{pr.number} · {pr.author}</div>
        </div>
        <CiMark pr={pr} />
        <QueueItemActions className="ml-0">
          <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} title="Abrir en GitHub" asChild>
            <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
          </QueueItemAction>
        </QueueItemActions>
      </div>
    </QueueItem>
  );
}

/** Módulo Stack: los stacks de PRs del desarrollo actual (abajo = la base), por repo. */
export function GithubPanel() {
  const session = useFolders((s) => s.tree.sessions.find((x) => x.id === s.activeId));
  const { activePrUrl, tree, setActive, setActivePr } = useFolders();
  const { gh, error } = useGithubReviews();
  const ghError = error ?? gh?.error ?? (gh && !gh.stacks ? "el server no manda los stacks: reinicia `ide`" : null);
  // la card de PR seleccionada manda; si no, la sesión abierta
  // click en una PR del stack: abre su desarrollo (su sesión, o la PR si está en las listas)
  const devs = desarrollos(tree.sessions, gh, tree.devPrs);
  const openDev = (pr: GhPr) => {
    const d = devs.find((x) => x.kind === "session" ? x.session.id === pr.sessionId : x.pr.url === pr.url);
    if (!d) return undefined;
    return () => d.kind === "session" ? setActive(d.session.id) : setActivePr(d.pr.url);
  };
  const prs = useDevPrs();
  const data = !gh || (!session && !activePrUrl) ? null : devStacks(prs, gh);
  return (
    <div className="flex w-full min-w-0 flex-col overflow-hidden">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Stack</div>
      {ghError && <p role="alert" className="mx-2.5 text-xs text-destructive">{ghError}</p>}
      {!session && !activePrUrl && <p className="mx-2.5 text-xs text-muted-foreground">Abre una sesión o elige una PR para ver su stack.</p>}
      {(session || activePrUrl) && !gh && !ghError && <p className="mx-2.5 text-xs text-muted-foreground">cargando…</p>}
      {data?.stacks.length === 0 && (
        <p className="mx-2.5 text-xs text-muted-foreground">
          {activePrUrl ? "La PR ya no está abierta." : `Las ramas de ${session!.id} no tienen PRs abiertas.`}</p>)}
      {data?.stacks.map((stack) => (
        <div key={stack[0].url} className="mb-2">
          <div className="mx-2.5 mb-0.5 font-mono text-[10px] text-muted-foreground">
            {stack[0].repo}{stack.length > 1 ? ` · stack de ${stack.length}` : ""}
          </div>
          <QueueList className="flex-col-reverse">
            {stack.map((pr) => <StackItem key={pr.url} pr={pr} own={data.own.has(pr.url)}
              onOpen={openDev(pr)}
              assigned={!gh?.me || pr.author === `@${gh.me}` || !!pr.reviewers?.some((r) => r.login === gh.me)} />)}
          </QueueList>
        </div>
      ))}
    </div>
  );
}
