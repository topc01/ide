// ui/src/modules/github/GithubPanel.tsx
import { ExternalLink } from "lucide-react";
import { useFolders } from "../../state/folders";
import type { FolderSession, GhPr, GithubReviews } from "../../transport/folderSessions";
import { QueueItem, QueueItemAction, QueueItemActions, QueueList } from "../../components/ai-elements/queue";
import { useGithubReviews } from "../sessions/ReviewsSection";
import { cn } from "../../lib/utils";

const REVIEW = {
  approved: ["bg-emerald-500", "aprobada"],
  review: ["bg-sky-500", "en revisión"],
  changes: ["bg-amber-400", "pidieron cambios"],
} as const;

function allPrs(gh: GithubReviews): GhPr[] {
  const lists = [gh.pending, gh.changesRequested, ...Object.values(gh.mine ?? {}), ...Object.values(gh.stacks ?? {})];
  const byUrl = new Map<string, GhPr>();
  for (const l of lists) for (const pr of l ?? []) byUrl.set(pr.url, pr);
  return [...byUrl.values()];
}

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

function StackItem({ pr, own }: { pr: GhPr; own: boolean }) {
  const [color, label] = pr.review ? REVIEW[pr.review] : [null, "sin review"];
  return (
    <QueueItem className="px-1.5">
      <div className={cn("flex items-center gap-1.5 rounded border-l-2 border-transparent px-1.5 py-1 text-xs hover:bg-accent/60",
        own && "border-primary bg-accent")} title={`${pr.title} — ${label}`}>
        <span aria-label={label} className={cn("h-2 w-2 shrink-0 rounded-full", color ?? "border border-muted-foreground")} />
        <span className="font-mono text-[10px] text-muted-foreground">{pr.stack?.position ?? 1}</span>
        <span className="min-w-0 flex-1 truncate">{pr.title}</span>
        <QueueItemActions className="ml-0">
          <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} asChild>
            <a href={pr.url} target="_blank" rel="noreferrer"><ExternalLink size={11} /></a>
          </QueueItemAction>
        </QueueItemActions>
      </div>
    </QueueItem>
  );
}

/** Módulo GitHub: el stack de PRs de la sesión abierta (abajo = la base). */
export function GithubPanel() {
  const session = useFolders((s) => s.tree.sessions.find((x) => x.id === s.activeId));
  const { gh, error } = useGithubReviews();
  const ghError = error ?? gh?.error ?? (gh && !gh.stacks ? "el server no manda los stacks: reinicia `ide`" : null);
  const data = session && gh ? sessionStacks(session, gh) : null;
  return (
    <div className="flex flex-col">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">GitHub</div>
      {ghError && <p role="alert" className="mx-2.5 text-xs text-destructive">{ghError}</p>}
      {!session && <p className="mx-2.5 text-xs text-muted-foreground">Abre una sesión para ver sus PRs.</p>}
      {session && !gh && !ghError && <p className="mx-2.5 text-xs text-muted-foreground">cargando…</p>}
      {data?.stacks.length === 0 && (
        <p className="mx-2.5 text-xs text-muted-foreground">Las ramas de {session!.id} no tienen PRs abiertas.</p>)}
      {data?.stacks.map((stack) => (
        <div key={stack[0].url} className="mb-2">
          <div className="mx-2.5 mb-0.5 font-mono text-[10px] text-muted-foreground">
            {stack[0].repo}{stack.length > 1 ? ` · stack de ${stack.length}` : ""}
          </div>
          <QueueList className="flex-col-reverse">
            {stack.map((pr) => <StackItem key={pr.url} pr={pr} own={data.own.has(pr.url)} />)}
          </QueueList>
        </div>
      ))}
    </div>
  );
}
