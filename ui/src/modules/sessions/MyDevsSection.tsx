// ui/src/modules/sessions/MyDevsSection.tsx
import { ExternalLink, Unlink } from "lucide-react";
import { unlinkPr } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { useDevTabs } from "../../state/devTabs";
import type { FolderSession, GhPr, MergeJob } from "../../transport/folderSessions";
import { QueueItem, QueueItemAction, QueueItemActions } from "../../components/ai-elements/queue";
import { CardActions, CardCorner, DevIndex, DevStateLabel, RenameAction, StateAction, CardShell, DepsPause, DevTitle, HideToggle, RefChip, devTone, repoShort, titlePad } from "./DevCard";
import { worstPr } from "./desarrollos";
import { CiMark, PrCard, useGithubReviews } from "./ReviewsSection";
import { canMerge, MERGE_ACTIVE, MergeButton, MergeStatus } from "./MergeControls";
import { SessionItem } from "./SessionItem";
import { RereviewAction } from "./ReviewVerdict";
import { GroupedSection, type Entry } from "./GroupedSection";
import { deriveMine, isHidden, type Desarrollo } from "./desarrollos";
import { BLOCKS, devStateOf, STATE, STATE_ORDER, type Block, type DevStateInfo } from "./devStates";
import { cn } from "../../lib/utils";

const DOT: Record<string, string> = {
  approved: "bg-emerald-400", changes: "bg-amber-300", review: "bg-sky-400",
};

/** Una PR dentro de un desarrollo con varias: punto de review, número, título, CI, ⏸, y en hover
 *  Mergear (solo la de abajo) y abrir en GitHub. Click = elegir esa PR. */
/** `sessionId`: la fila está en la card de una sesión: se puede sacar de ese desarrollo. */
export function PrRow({ pr, job, bottom, sessionId }: { pr: GhPr; job?: MergeJob; bottom: boolean; sessionId?: string }) {
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
        {sessionId && (
          <QueueItemAction aria-label={`Sacar ${pr.repo}#${pr.number} de este desarrollo`}
            title="Sacar esta PR de este desarrollo (pasa a ser un desarrollo aparte; no toca GitHub)"
            onClick={(e) => { e.stopPropagation(); unlinkPr(getWs(), sessionId, pr.url).catch(() => {}); }}>
            <Unlink size={11} />
          </QueueItemAction>)}
      </span>
    </div>
  );
}

/** Stack tuyo sin sesión: una card con una fila por PR (de abajo hacia arriba). */
function StackCard({ d, dev }: { d: Desarrollo; dev: DevStateInfo | null }) {
  const { gh } = useGithubReviews();
  const activePrUrl = useFolders((s) => s.activePrUrl);
  const setActivePr = useFolders((s) => s.setActivePr);
  const bottom = d.prs[0];
  const tone = devTone(bottom, gh?.merges?.[bottom.url]);
  return (
    <QueueItem className="px-2 py-1">
      <CardShell tone={tone} dev={dev} selected={d.prs.some((p) => p.url === activePrUrl)} dashed onClick={() => {
        // volver al stack como lo dejaste: la PR de la tab activa (si no, la de abajo)
        const t = useDevTabs.getState().byDev[`st:${bottom.stack?.id}`];
        const last = t?.tabs.find((x) => x.id === t.active)?.url;
        setActivePr(last && d.prs.some((p) => p.url === last) ? last : bottom.url);
      }}>
        <CardCorner><DepsPause pr={bottom} />{worstPr(d.prs).ci && <CiMark pr={worstPr(d.prs).ci!} />}</CardCorner>
        <div className={cn("flex items-start gap-1.5", titlePad(bottom))}>
          <DevTitle devKey={d.key} prs={d.prs} original={bottom.title} />
          <CardActions><RenameAction devKey={d.key} /><StateAction dev={dev} devKey={d.key} /><RereviewAction prs={d.prs} /><HideToggle devKey={d.key} prs={d.prs} /></CardActions>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1" title={`stack de ${d.prs.length} (de abajo hacia arriba)`}>
          <DevIndex devKey={d.key} prs={d.prs} />
          {d.prs.map((p) => <RefChip key={p.url} repo={p.repo} number={p.number} pr={p} />)}
        </div>
        {dev && <div className="mt-1 flex flex-wrap gap-x-2 text-[11px]"><DevStateLabel dev={dev} devKey={d.key} /></div>}
      </CardShell>
    </QueueItem>
  );
}

/** Los grupos: todos los estados en su orden, pero solo los que tienen algo (los bloqueos se ven siempre:
 *  son lo que hay que destrabar). */
const statusesFor = (present: Set<string>): [string, string][] =>
  STATE_ORDER.filter((k) => present.has(k) || (BLOCKS.includes(k as Block) && k !== "paused")).map((k) => [k, STATE[k][0]]);

/** Mis desarrollos: sesiones de ticket y PRs propias unificadas (una card por desarrollo). */
export function MyDevsSection({ tickets }: { tickets: FolderSession[] }) {
  const { gh, error } = useGithubReviews();
  const links = useFolders((s) => s.tree.devPrs);
  const states = useFolders((s) => s.tree.devStates);
  const devs = deriveMine(tickets, gh, links);
  const hiddenKeys = useFolders((s) => s.tree.devHidden);
  const ghError = error ?? gh?.error;
  const all: (Entry & { hidden: boolean })[] = devs.map((d) => {
    const dev = devStateOf(states, d.key, d.prs, d.job ?? (d.prs[0] ? gh?.merges?.[d.prs[0].url] : undefined), d.merged);
    return {
    key: d.key, pr: d.prs[0], session: d.session, status: dev.state,
    hidden: d.status !== "merges" && !!isHidden(hiddenKeys, d.key, d.prs),
    render: () => d.session ? <SessionItem session={d.session} prs={d.prs} merged={d.merged} dev={dev} actions={<><RereviewAction prs={d.prs} /><HideToggle devKey={d.key} prs={d.prs} /></>} />
      : d.prs.length > 1 ? <StackCard d={d} dev={dev} />
      : <PrCard pr={d.prs[0]} devKey={d.key} dev={dev} showReviewers extraActions={<><RereviewAction prs={d.prs} /><HideToggle devKey={d.key} prs={d.prs} /></>} merge={{
          job: d.job ?? gh?.merges?.[d.prs[0].url],
          above: d.prs[0].stack ? d.prs[0].stack.size - d.prs[0].stack.position : 0 }} />,
  }; });
  return (
    <GroupedSection id="mine" title="Mis desarrollos" entries={all.filter((e) => !e.hidden)}
      hidden={all.filter((e) => e.hidden)} gh={gh}
      statuses={statusesFor(new Set(all.filter((e) => !e.hidden).map((e) => e.status)))}
      status={<>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
      </>} />
  );
}
