// ui/src/modules/sessions/MyDevsSection.tsx
import { ExternalLink } from "lucide-react";
import { useFolders } from "../../state/folders";
import { useDevTabs } from "../../state/devTabs";
import type { FolderSession, GhPr, MergeJob } from "../../transport/folderSessions";
import { QueueItem, QueueItemAction } from "../../components/ai-elements/queue";
import { CardShell, DepsPause, devTone, repoShort } from "./DevCard";
import { CiMark, PrCard, useGithubReviews } from "./ReviewsSection";
import { canMerge, MERGE_ACTIVE, MergeButton, MergeStatus } from "./MergeControls";
import { SessionItem } from "./SessionItem";
import { GroupedSection, type Entry } from "./GroupedSection";
import { deriveMine, type Desarrollo } from "./desarrollos";
import { cn } from "../../lib/utils";

const DOT: Record<string, string> = {
  approved: "bg-emerald-400", changes: "bg-amber-300", review: "bg-sky-400",
};

/** Una PR dentro de un desarrollo con varias: punto de review, número, título, CI, ⏸, y en hover
 *  Mergear (solo la de abajo) y abrir en GitHub. Click = elegir esa PR. */
export function PrRow({ pr, job, bottom }: { pr: GhPr; job?: MergeJob; bottom: boolean }) {
  const active = useFolders((s) => s.activePrUrl === pr.url);
  const setActivePr = useFolders((s) => s.setActivePr);
  const merging = !!job && MERGE_ACTIVE.includes(job.state);
  return (
    <div onClick={(e) => { e.stopPropagation(); setActivePr(pr.url); }}
      title={`${pr.repo}#${pr.number}: ${pr.title}`}
      className={cn("group/row -mx-1 flex min-w-0 items-center gap-1.5 rounded px-1 py-0.5 hover:bg-accent/50",
        active && "bg-accent/70")}>
      <span className={cn("h-2 w-2 shrink-0 rounded-full", pr.review ? DOT[pr.review] : "border border-muted-foreground")} />
      <span className="shrink-0 font-mono text-[11px] font-bold">#{pr.number}</span>
      <span className="min-w-0 flex-1 truncate">{pr.title}</span>
      {job && <MergeStatus url={pr.url} job={job} />}
      <CiMark pr={pr} />
      <DepsPause pr={pr} />
      <span className="flex shrink-0 items-center opacity-0 group-hover/row:opacity-100">
        {bottom && canMerge(pr) && !merging && job?.state !== "done"
          && <MergeButton pr={pr} above={pr.stack ? pr.stack.size - pr.stack.position : 0} />}
        <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} title="Abrir en GitHub" asChild>
          <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
        </QueueItemAction>
      </span>
    </div>
  );
}

/** Stack tuyo sin sesión: una card con una fila por PR (de abajo hacia arriba). */
function StackCard({ d }: { d: Desarrollo }) {
  const { gh } = useGithubReviews();
  const activePrUrl = useFolders((s) => s.activePrUrl);
  const setActivePr = useFolders((s) => s.setActivePr);
  const bottom = d.prs[0];
  const tone = devTone(bottom, gh?.merges?.[bottom.url]);
  return (
    <QueueItem className="px-2 py-1">
      <CardShell tone={tone} selected={d.prs.some((p) => p.url === activePrUrl)} dashed onClick={() => {
        // volver al stack como lo dejaste: la PR de la tab activa (si no, la de abajo)
        const t = useDevTabs.getState().byDev[`st:${bottom.stack?.id}`];
        const last = t?.tabs.find((x) => x.id === t.active)?.url;
        setActivePr(last && d.prs.some((p) => p.url === last) ? last : bottom.url);
      }}>
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[11px] font-bold tracking-wide">{repoShort(bottom.repo)}</span>
          <span className="text-[11px] text-muted-foreground">stack de {d.prs.length}</span>
        </div>
        <div className="mt-1 space-y-0.5">
          {d.prs.map((p, i) => <PrRow key={p.url} pr={p} job={gh?.merges?.[p.url]} bottom={i === 0} />)}
        </div>
      </CardShell>
    </QueueItem>
  );
}

const STATUSES: [string, string][] = [
  ["merges", "Merges"], ["returned", "Devueltas"], ["waiting", "Esperando revisores"],
  ["missing", "Sin revisores"], ["draft", "Draft"], ["approved", "Aprobadas"], ["nopr", "Sin PR"],
];

/** Mis desarrollos: sesiones de ticket y PRs propias unificadas (una card por desarrollo). */
export function MyDevsSection({ tickets }: { tickets: FolderSession[] }) {
  const { gh, error } = useGithubReviews();
  const devs = deriveMine(tickets, gh);
  const ghError = error ?? gh?.error;
  const entries: Entry[] = devs.map((d) => ({
    key: d.key, pr: d.prs[0], session: d.session, status: d.status,
    render: () => d.session ? <SessionItem session={d.session} prs={d.prs} />
      : d.prs.length > 1 ? <StackCard d={d} />
      : <PrCard pr={d.prs[0]} showReviewers merge={{
          job: d.job ?? gh?.merges?.[d.prs[0].url],
          above: d.prs[0].stack ? d.prs[0].stack.size - d.prs[0].stack.position : 0 }} />,
  }));
  return (
    <GroupedSection id="mine" title="Mis desarrollos" entries={entries} gh={gh}
      statuses={STATUSES.filter(([k]) => k !== "merges" || devs.some((d) => d.status === "merges"))}
      status={<>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
      </>} />
  );
}
