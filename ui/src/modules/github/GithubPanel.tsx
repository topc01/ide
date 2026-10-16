// ui/src/modules/github/GithubPanel.tsx
import { ExternalLink } from "lucide-react";
import { useFolders } from "../../state/folders";
import type { FolderSession, GhPr, GithubReviews } from "../../transport/folderSessions";
import { QueueItem, QueueItemAction, QueueItemActions, QueueList } from "../../components/ai-elements/queue";
import { allPrs, CiMark, useGithubReviews } from "../sessions/ReviewsSection";
import { cn } from "../../lib/utils";

const REVIEW = {
  approved: ["bg-emerald-500", "aprobada"],
  review: ["bg-sky-500", "en revisión"],
  changes: ["bg-amber-400", "pidieron cambios"],
} as const;

/** Las PRs de la sesión: la del PR revisado, o las de las ramas de sus repos; cada una con su stack. */
function sessionStacks(s: FolderSession, gh: GithubReviews): { own: Set<string>; stacks: GhPr[][] } {
  const prs = allPrs(gh);
  const own = prs.filter((p) => p.sessionId === s.id
    || s.repos.some((r) => r.branch && p.repo === r.name && p.head === r.branch));
  const seen = new Set<string>();
  const stacks: GhPr[][] = [];
  for (const p of own) {
    const key = p.stack?.id ?? p.url;
    if (seen.has(key)) continue;
    seen.add(key);
    stacks.push(p.stack ? gh.stacks?.[p.stack.id] ?? [p] : [p]);
  }
  return { own: new Set(own.map((p) => p.url)), stacks };
}

/** `assigned`: la PR es tuya (autor) o figuras como revisor; si no, va tachada y atenuada. */
function StackItem({ pr, own, assigned }: { pr: GhPr; own: boolean; assigned: boolean }) {
  const [color, label] = pr.review ? REVIEW[pr.review] : [null, "sin review"];
  return (
    <QueueItem className="min-w-0 px-1.5">
      <div className={cn("flex min-w-0 items-start gap-1.5 rounded border-l-2 border-transparent px-1.5 py-1 text-xs hover:bg-accent/60",
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
            <a href={pr.url} target="_blank" rel="noreferrer"><ExternalLink size={11} /></a>
          </QueueItemAction>
        </QueueItemActions>
      </div>
    </QueueItem>
  );
}

/** Módulo GitHub: el stack de PRs de la sesión abierta (abajo = la base). */
function prStacks(url: string, gh: GithubReviews): { own: Set<string>; stacks: GhPr[][] } {
  const pr = allPrs(gh).find((p) => p.url === url);
  if (!pr) return { own: new Set(), stacks: [] };
  return { own: new Set([url]), stacks: [pr.stack ? gh.stacks?.[pr.stack.id] ?? [pr] : [pr]] };
}

export function GithubPanel() {
  const session = useFolders((s) => s.tree.sessions.find((x) => x.id === s.activeId));
  const activePrUrl = useFolders((s) => s.activePrUrl);
  const { gh, error } = useGithubReviews();
  const ghError = error ?? gh?.error ?? (gh && !gh.stacks ? "el server no manda los stacks: reinicia `ide`" : null);
  // la card de PR seleccionada manda; si no, la sesión abierta
  const data = !gh ? null : activePrUrl ? prStacks(activePrUrl, gh) : session ? sessionStacks(session, gh) : null;
  return (
    <div className="flex w-full min-w-0 flex-col overflow-hidden">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">GitHub</div>
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
              assigned={!gh?.me || pr.author === `@${gh.me}` || !!pr.reviewers?.some((r) => r.login === gh.me)} />)}
          </QueueList>
        </div>
      ))}
    </div>
  );
}
