// ui/src/modules/github/GithubPanel.tsx
import { useEffect, useState } from "react";
import { ArrowUpRight, ExternalLink } from "lucide-react";
import { diffTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import { prFiles, restackStack, type MergeJob, type PrFile } from "../../transport/folderSessions";
import { canMerge, MERGE_ACTIVE, MergeButton, MergeStatus } from "../sessions/MergeControls";
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

const STATUS: Record<string, [string, string, string]> = {
  A: ["A", "text-emerald-400", "nuevo"], M: ["M", "text-amber-300", "modificado"], D: ["D", "text-red-400", "borrado"],
  R: ["R", "text-sky-300", "renombrado"], "?": ["?", "text-emerald-300", "sin trackear (worktree local)"],
};

/** Archivos cambiados de una PR (contra su base; en un stack, la de abajo), bajo su rama: nombre,
 *  carpeta debajo y +/−. Click = su diff en una tab; el que estás viendo, destacado. */
function PrChanges({ pr }: { pr: GhPr }) {
  const dev = useCurrentDev();
  const open = useDevTabs((s) => s.open);
  const active = useDevTabs((s) => dev ? s.byDev[dev.key]?.active : null);
  const [files, setFiles] = useState<PrFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    prFiles(getWs(), pr.url).then((d) => setFiles(d.files)).catch((e: any) => setError(e?.message ?? String(e)));
  }, [pr.url]);
  if (error) return <p role="alert" className="mx-3 mb-2 text-[11px] text-destructive">{error}</p>;
  if (!files) return <p className="mx-3 mb-2 text-[11px] text-muted-foreground">trayendo los cambios…</p>;
  if (!files.length) return <p className="mx-3 mb-2 text-[11px] text-muted-foreground">Sin cambios contra {pr.base}.</p>;
  return (
    <div className="mb-2 ml-3 mr-1 border-l border-border">
      {files.map((f) => {
        const [letter, cls, what] = STATUS[f.status] ?? [f.status, "text-muted-foreground", f.status];
        const slash = f.path.lastIndexOf("/");
        const on = active === `diff:${pr.url}:${f.path}`;
        return (
          <button key={f.path} title={`${what}: ${f.oldPath ? `${f.oldPath} → ` : ""}${f.path}`}
            onClick={() => dev && open(dev.key, diffTab(pr.url, f.path, f.oldPath))}
            className={cn("flex w-full min-w-0 items-start gap-2 py-1 pl-2.5 pr-1.5 text-left hover:bg-accent/60",
              on && "bg-accent")}>
            <span className={cn("mt-px w-2.5 shrink-0 font-mono text-[11px] font-bold", cls)}>{letter}</span>
            <span className="min-w-0 flex-1">
              <span className={cn("block truncate font-mono text-[11px]", on ? "font-semibold text-foreground" : "text-foreground/90")}>
                {f.path.slice(slash + 1)}</span>
              {slash >= 0 && <span className="block truncate font-mono text-[10px] text-muted-foreground"
                style={{ direction: "rtl", textAlign: "left" }}>{f.path.slice(0, slash)}</span>}
            </span>
            {(f.additions > 0 || f.deletions > 0) && <span className="mt-px shrink-0 font-mono text-[10px]">
              <span className="text-emerald-400">+{f.additions}</span> <span className="text-red-400">−{f.deletions}</span></span>}
          </button>);
      })}
    </div>
  );
}

/** Una PR del stack: click despliega sus archivos cambiados bajo la rama; destacada la que tienes
 *  abierta. destacada la que estás viendo.
 *  `assigned`: tuya o figuras como revisor (si no, va tachada y atenuada). Mergear en la de abajo si es
 *  tuya y está aprobada. */
function StackItem({ pr, own, assigned, onGoto, viewing, onOpen, mine, job, above }:
  { pr: GhPr; own: boolean; assigned: boolean; onGoto?: () => void; viewing: boolean; onOpen: () => void;
    mine: boolean; job?: MergeJob; above: number }) {
  const [color, label] = pr.review ? REVIEW[pr.review] : [null, "sin review"];
  const merging = !!job && MERGE_ACTIVE.includes(job.state);
  return (
    <QueueItem className="min-w-0 px-1.5">
      <div onClick={onOpen} title={viewing ? "Ocultar los archivos cambiados" : "Ver los archivos cambiados de esta PR"}
        className={cn("flex min-w-0 cursor-pointer items-start gap-1.5 rounded border-l-2 border-transparent px-1.5 py-1 text-xs hover:bg-accent/60",
          viewing && "border-primary bg-accent", !assigned && "opacity-50")}>
        <span aria-label={label} title={label}
          className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", color ?? "border border-muted-foreground")} />
        <span className="mt-px font-mono text-[10px] text-muted-foreground">{pr.stack?.position ?? 1}</span>
        <div className="min-w-0 flex-1">
          <div className={cn("truncate", !assigned && "line-through")}
            title={assigned ? pr.title : `${pr.title} (no asignada a ti)`}>{pr.title}</div>
          <div className="truncate font-mono text-[10px] text-muted-foreground" title={`${pr.repo}#${pr.number} · ${pr.author} · ${pr.head} → ${pr.base}`}>
            {pr.repo}#{pr.number} · {pr.head}</div>
          {job && <MergeStatus url={pr.url} job={job} />}
        </div>
        <CiMark pr={pr} />
        <QueueItemActions className="ml-0">
          {mine && canMerge(pr) && !merging && job?.state !== "done" && <MergeButton pr={pr} above={above} />}
          {onGoto && !own && (
            <QueueItemAction aria-label={`Ir al desarrollo de ${pr.repo}#${pr.number}`} title="Ir al desarrollo de esta PR"
              onClick={(e) => { e.stopPropagation(); onGoto(); }}><ArrowUpRight size={11} /></QueueItemAction>)}
          <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} title="Abrir en GitHub" asChild>
            <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
          </QueueItemAction>
        </QueueItemActions>
      </div>
      {viewing && <PrChanges pr={pr} />}
    </QueueItem>
  );
}

/** Restack / actualizar desde la base: reescribe ramas (push forzado), así que pide confirmar. */
function StackActions({ stack, base }: { stack: GhPr[]; base: string }) {
  const [confirm, setConfirm] = useState<"restack" | "base" | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const run = (updateBase: boolean) => {
    setConfirm(null); setBusy(true); setMsg(null);
    restackStack(getWs(), stack[0].url, updateBase)
      .then((r) => setMsg(r.moved.length ? `movidas: ${r.moved.join(", ")}` : "ya estaba al día"))
      .catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`)).finally(() => setBusy(false));
  };
  const btn = "rounded border border-border px-1.5 py-px text-[10px] hover:bg-accent disabled:opacity-40";
  return (
    <div className="mx-2.5 mb-1">
      <div className="flex flex-wrap items-center gap-1">
        {confirm ? (<>
          <span className="text-[10px] text-amber-300">
            {confirm === "restack" ? "Rebasear cada PR sobre la de abajo" : `Rebasear el stack sobre ${base}`} y empujar con --force-with-lease?</span>
          <button className={cn(btn, "border-amber-400/60 text-amber-300")} disabled={busy} onClick={() => run(confirm === "base")}
            title="Sí, rebasear y empujar">Sí</button>
          <button className={btn} onClick={() => setConfirm(null)} title="No">No</button>
        </>) : (<>
          {stack.length > 1 && <button className={btn} disabled={busy} onClick={() => setConfirm("restack")}
            title="Rebasear cada PR sobre la de abajo (tras cambios en una PR de más abajo)">Restack</button>}
          <button className={btn} disabled={busy} onClick={() => setConfirm("base")}
            title={`Rebasear ${stack.length > 1 ? "todo el stack" : "la rama"} sobre lo último de ${base}`}>Actualizar desde {base}</button>
          {busy && <span className="text-[10px] text-muted-foreground">rebaseando…</span>}
        </>)}
      </div>
      {msg && <p role={msg.startsWith("⚠") ? "alert" : undefined}
        className={cn("mt-0.5 text-[10px]", msg.startsWith("⚠") ? "text-destructive" : "text-muted-foreground")}>{msg}</p>}
    </div>
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
  const [expanded, setExpanded] = useState<string | null>(null);   // PR con los archivos desplegados
  // precarga: el server trae las PRs en segundo plano y el click después es inmediato
  const urls = prs.map((p) => p.url).join(" ");
  useEffect(() => { for (const u of urls.split(" ").filter(Boolean)) prFiles(getWs(), u).catch(() => {}); }, [urls]);
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
          {stack.every((p) => gh?.me && p.author === `@${gh.me}`) && <StackActions stack={stack} base={stack[0].base ?? "develop"} />}
          <QueueList className="flex-col-reverse">
            {stack.map((pr) => <StackItem key={pr.url} pr={pr} own={data.own.has(pr.url)}
              onGoto={openDev(pr)} viewing={expanded === pr.url}
              onOpen={() => setExpanded(expanded === pr.url ? null : pr.url)}
              mine={!!gh?.me && pr.author === `@${gh.me}`} job={gh?.merges?.[pr.url]}
              above={pr.stack ? pr.stack.size - pr.stack.position : 0}
              assigned={!gh?.me || pr.author === `@${gh.me}` || !!pr.reviewers?.some((r) => r.login === gh.me)} />)}
          </QueueList>
        </div>
      ))}
    </div>
  );
}
