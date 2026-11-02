// ui/src/modules/sessions/ReviewsSection.tsx
import { useEffect, useState } from "react";
import { Archive, ArrowRightLeft, Check, ChevronRight, ExternalLink, Layers, Layers2, Link2, Loader2, MoreHorizontal, Plus, ScanEye, Unlink, X } from "lucide-react";
import { Collapsible } from "radix-ui";
import { useFolders } from "../../state/folders";
import {
  archiveSession, dismissMerge, fetchGithubReviews, onGithubReviews, setReviewers, startReview, startStackReview, unlinkPr, type MergeJob, type FolderSession, type GhPr, type GithubReviews,
} from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { QueueList, QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { SessionItem } from "./SessionItem";
import { MovePrAction } from "./MyDevsSection";
import { waitingFirst } from "./activity";
import { ReviewVerdictActions } from "./ReviewVerdict";
import { GroupedSection, type Entry } from "./GroupedSection";
import { canMerge, MERGE_ACTIVE, MergeButton, MergeStatus } from "./MergeControls";
import { CardActions, CardCorner, DevIndex, LaterChip, DevStateLabel, RenameAction, StateAction, CardShell, DepsPause, DevTitle, RefChip, devTone, repoShort, titlePad } from "./DevCard";
import { cn } from "../../lib/utils";
import type { DevStateInfo } from "./devStates";
import { PersonChip } from "../../lib/people";
import { usePersistentOpen } from "../../lib/persist";

/** "Archivar todas" en el grupo Cerradas de Revisiones: archiva las sesiones de revisión de PRs ya
 *  mergeadas o cerradas (para su claude y deja su carpeta en .ide/archive). Pide confirmar. */
function ArchiveClosed({ sessions }: { sessions: FolderSession[] }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!sessions.length) return null;
  const go = async () => {
    setBusy(true); setErr(null);
    const failed: string[] = [];
    for (const s of sessions) {
      try { await archiveSession(getWs(), s.id, true); } catch (e: any) { failed.push(`${s.id}: ${e?.message ?? e}`); }
    }
    setBusy(false);
    if (failed.length) setErr(failed.join("\n")); else setOpen(false);
  };
  return (<>
    <button aria-label="Archivar todas las cerradas" title={`Archivar las ${sessions.length} revisiones de PRs ya cerradas o mergeadas`}
      onClick={(e) => { e.stopPropagation(); setOpen(true); }}
      className="mr-1 grid h-5 w-5 shrink-0 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground">
      <Archive size={12} /></button>
    {open && (
      <Dialog open onOpenChange={(o) => { if (!o) setOpen(false); }}>
        <DialogContent onClick={(e) => e.stopPropagation()} className="max-w-md">
          <DialogHeader><DialogTitle className="text-sm">¿Archivar {sessions.length} revisiones cerradas?</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">Son de PRs ya mergeadas o cerradas. Se para su claude y su carpeta pasa a
            .ide/archive (no toca GitHub).</p>
          <ul className="max-h-48 space-y-0.5 overflow-auto text-xs">
            {sessions.map((s) => <li key={s.id} className="truncate"><span className="font-mono">{s.id}</span> <span className="text-muted-foreground">{s.title}</span></li>)}
          </ul>
          {err && <p role="alert" className="whitespace-pre-wrap text-xs text-destructive">⚠ {err}</p>}
          <DialogFooter className="gap-2">
            <Button size="sm" variant="ghost" title="No archivar" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={busy} title="Archivar todas" onClick={go}>{busy ? "Archivando…" : `Archivar ${sessions.length}`}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>)}
  </>);
}

/** "Revisar stack": una sola sesión que revisa, de abajo hacia arriba, las PRs de este stack que te
 *  pidieron revisar (las sesiones individuales de esas PRs se archivan). Pide confirmar. */
function StackReviewButton({ prs }: { prs: GhPr[] }) {
  const setActive = useFolders((s) => s.setActive);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const go = () => {
    setBusy(true); setError(null);
    startStackReview(getWs(), prs.map((p) => p.url)).then((r) => { setOpen(false); setActive(r.id); })
      .catch((err: any) => setError(err?.message ?? String(err))).finally(() => setBusy(false));
  };
  return (<>
    <QueueItemAction aria-label="Revisar stack" title={`Revisar el stack completo en una sesión (${prs.length} PRs, de abajo hacia arriba)`}
      onClick={(e) => { e.stopPropagation(); setOpen(true); }}><Layers size={11} /></QueueItemAction>
    {open && (
      <Dialog open onOpenChange={(o) => { if (!o) setOpen(false); }}>
        <DialogContent onClick={(e) => e.stopPropagation()} className="max-w-md">
          <DialogHeader><DialogTitle className="text-sm">¿Revisar el stack en una sola sesión?</DialogTitle></DialogHeader>
          <ol className="list-decimal space-y-0.5 pl-5 text-xs">
            {prs.map((p) => <li key={p.url}><span className="font-mono font-bold">{repoShort(p.repo)} #{p.number}</span> {p.title}</li>)}
          </ol>
          <p className="text-[11px] text-muted-foreground">Las revisa de abajo hacia arriba y al final te pide OK para publicar. Si alguna ya
            tiene su sesión de revisión, se archiva.</p>
          {error && <p role="alert" className="text-xs text-destructive">⚠ {error}</p>}
          <DialogFooter className="gap-2">
            <Button size="sm" variant="ghost" title="No" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button size="sm" disabled={busy} title="Crear la sesión del stack y empezar" onClick={go}>{busy ? "Creando…" : "Revisar stack"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>)}
  </>);
}

/** ⚠ sync: la última resincronización completa de PRs no se aceptó (GitHub respondió vacío o a
 *  medias): no se borró nada y se reintenta; los números en el tooltip. */
export function SyncWarning({ gh }: { gh: GithubReviews | null }) {
  const s = gh?.sync;
  if (!s || s.ok) return null;
  const when = new Date(s.at).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  return <span role="alert" className="truncate text-[10px] text-amber-300"
    title={`La resincronización de PRs de las ${when} vino rara: GitHub devolvió ${s.nodes} PRs (dice que hay ${s.issueCount}) `
      + `y había ${s.cached} guardadas; habría sacado ${s.gone}. No se borró nada y se reintenta en el próximo ciclo. `
      + `Si se repite, puede faltar o sobrar alguna PR en las cards.`}>⚠ sync</span>;
}

/** Botón de revisión: envía `.ide/prompts/review-pr.md` a la sesión del PR (la crea si falta). */
function ReviewButton({ pr }: { pr: GhPr }) {
  const setActive = useFolders((s) => s.setActive);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (<>
    {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
    <QueueItemAction aria-label={`Revisar ${pr.sessionId}`} title="Revisar (envía el prompt review-pr)"
      disabled={busy}
      onClick={(e) => {
        e.stopPropagation();
        setBusy(true); setError(null);
        startReview(getWs(), pr.url).then((r) => setActive(r.id))
          .catch((err: any) => setError(err?.message ?? String(err))).finally(() => setBusy(false));
      }}>
      <ScanEye size={11} />
    </QueueItemAction>
  </>);
}

/** Estado de GitHub (revisiones + mis PRs), compartido por las secciones de la sidebar. */
export function useGithubReviews(): { gh: GithubReviews | null; error: string | null } {
  const [gh, setGh] = useState<GithubReviews | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const ws = getWs();
    fetchGithubReviews(ws).then(setGh).catch((e: any) => setError(e?.message ?? String(e)));
    return onGithubReviews(ws, (r) => { setGh(r); setError(null); });
  }, []);
  // recién arrancado, el server todavía no consultó GitHub: es "cargando", no "cero PRs"
  return { gh: gh && (gh.lastOk || gh.error) ? gh : null, error };
}

/** Todas las PRs que conoce el server (listas + stacks), sin repetir. */
export function allPrs(gh: GithubReviews): GhPr[] {
  const lists = [gh.pending, gh.changesRequested, ...Object.values(gh.mine ?? {}), ...Object.values(gh.stacks ?? {})];
  const byUrl = new Map<string, GhPr>();
  for (const l of lists) for (const pr of l ?? []) byUrl.set(pr.url, pr);
  return [...byUrl.values()];
}

const REVIEWER_TONE = {
  requested: ["border-amber-400/60 text-amber-300", "review pedida"],
  approved: ["border-emerald-500/60 text-emerald-400", "aprobó"],
  changes: ["border-red-500/60 text-red-400", "pidió cambios"],
} as const;

/** Badge de posición en el stack (1 = la de abajo). */
export function StackBadge({ pr }: { pr: GhPr }) {
  if (!pr.stack) return null;
  return (
    <span className="flex items-center gap-0.5 text-primary" title="posición en el stack (1 = la de abajo)">
      <Layers2 size={10} />{pr.stack.position}/{pr.stack.size}</span>
  );
}

/** Dependencias declaradas en "## Dependencias": ⛓ N ámbar si faltan N por mergear, ⛓ ✓ si no. */
export function DepsBadge({ pr }: { pr: GhPr }) {
  if (!pr.deps?.length) return null;
  const pending = pr.deps.filter((d) => d.state !== "MERGED" && !d.together);
  const together = pr.deps.filter((d) => d.together);
  const tip = [
    pending.length ? `Falta mergear: ${pending.map((d) => `${d.repo}#${d.number}`).join(", ")}` : "Dependencias mergeadas",
    together.length ? `Van juntas: ${together.map((d) => `${d.repo}#${d.number}`).join(", ")}` : "",
  ].filter(Boolean).join("\n");
  return (
    <span title={tip} className={cn("flex items-center gap-0.5 font-semibold",
      pending.length ? "text-amber-300" : "text-emerald-400")}>
      <Link2 size={10} />{pending.length ? pending.length : "✓"}{together.length ? <span className="text-sky-400">⇄</span> : null}
    </span>
  );
}

const DEP_STATE = {
  MERGED: ["✓", "text-purple-400", "mergeada"], OPEN: ["◌", "text-amber-300", "abierta: falta mergear"],
  CLOSED: ["✗", "text-red-500", "cerrada sin mergear"], UNKNOWN: ["?", "text-muted-foreground", "estado desconocido"],
} as const;

/** Cadena completa de dependencias (módulo Revisión, vista de PR, diálogo de merge). */
export function DepsList({ pr, onlyPending = false }: { pr: GhPr; onlyPending?: boolean }) {
  const deps = (pr.deps ?? []).filter((d) => !onlyPending || (d.state !== "MERGED" && !d.together));
  if (!deps.length) return null;
  const name = (url: string | null) => {
    const d = pr.deps?.find((x) => x.url === url);
    return d ? `${d.repo}#${d.number}` : "";
  };
  return (
    <ul className="space-y-0.5">
      {deps.map((d) => {
        const [mark, cls, label] = d.together ? ["⇄", "text-sky-400", "van juntas (se piden mutuamente)"] : DEP_STATE[d.state];
        return (
          <li key={d.url} className="group/c flex min-w-0 items-center gap-1.5 text-[11px]">
            <span className={cn("w-3 shrink-0 text-center font-bold", cls)} title={label}>{mark}</span>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{d.repo}#{d.number}</span>
            <span className="min-w-0 flex-1 truncate" title={d.title ?? ""}>{d.title}</span>
            {d.via && <span className="shrink-0 text-[10px] text-muted-foreground" title="Dependencia indirecta">vía {name(d.via)}</span>}
            <a href={d.url} target="_blank" rel="noreferrer" title="Abrir en GitHub" aria-label="Abrir en GitHub"
              className="shrink-0 text-muted-foreground opacity-0 hover:text-foreground group-hover/c:opacity-100"><ExternalLink size={10} /></a>
          </li>);
      })}
    </ul>
  );
}

/** CI de la PR: ✓ pasó, ✗ falló (tests, conflicto con la base, …), ◌ corriendo. */
export function CiMark({ pr }: { pr: GhPr }) {
  // marcas de esquina (como el ⏸): CI ✓ verde · ✗ roja falló (con pulso: falló pero quedan checks
  // corriendo) · ⟳ amarilla corriendo · ▫ gris en draft (punto rojo si falló un check liviano); aparte, ⚠ conflicto con la base y ⇣ atrasada (develop avanzó)
  const marks = [];
  if (pr.draft) {
    // en draft los tests no corren (quedan en "skipping"): solo los checks livianos (CI Gate, styleguide).
    // Cuadrado gris con un punto: gris si esos pasaron (o no hay), rojo si alguno falló.
    const failed = pr.ci === "failure";
    const label = `Draft: el CI de verdad (tests) corre al salir de draft${failed ? " · falló un check liviano (CI Gate o styleguide): míralo en GitHub"
      : pr.ci === "pending" ? " · corriendo los checks livianos" : ""}`;
    marks.push(
      <span key="ci" aria-label={label} title={label} className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded bg-zinc-500/15">
        <span className={cn("h-1.5 w-1.5 rounded-full", failed ? "bg-red-500" : "bg-muted-foreground")} />
      </span>);
  } else if (pr.ci) {
    const [Icon, cls, label] = pr.ci === "success" ? [Check, "bg-emerald-500/15 text-emerald-400", "CI pasó"]
      : pr.ci === "pending" ? [Loader2, "bg-amber-400/15 text-amber-300", "CI corriendo"]
      : [X, "bg-red-500/20 text-red-500", pr.ciRunning ? "CI falló (un check falló; otros siguen corriendo)" : "CI falló"];
    marks.push(
      <span key="ci" aria-label={label} title={label} className={cn("grid h-[18px] w-[18px] shrink-0 place-items-center rounded", cls,
        pr.ci === "failure" && pr.ciRunning && "animate-pulse")}>
        <Icon size={12} strokeWidth={3} className={pr.ci === "pending" ? "animate-spin" : undefined} />
      </span>);
  }
  if (pr.conflict) marks.push(
    <span key="conflict" aria-label="conflicto con la base" title={`Conflicto con ${pr.base ?? "su base"}: hay que resolverlo (no se puede mergear)`}
      className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded bg-red-500/20 text-[11px] font-bold text-red-400">⚠</span>);
  else if (pr.behind) marks.push(
    <span key="behind" aria-label="atrasada" title={`Atrasada respecto de ${pr.base ?? "su base"} (avanzó desde que se abrió): no bloquea, salvo que GitHub exija la rama al día`}
      className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded bg-amber-400/15 text-[11px] font-bold text-amber-300">⇣</span>);
  return marks.length ? <>{marks}</> : null;
}

/** Quién revisa la PR, con el color de su estado. */
const REVIEW_ICON = {
  requested: ["◌", "review pedida"], approved: ["✓", "aprobó"], changes: ["✗", "pidió cambios"],
} as const;

/** Revisor: chip con el color de la persona y su estado como ícono (✓ aprobó, ✗ cambios, ◌ pendiente). */
export function ReviewerChip({ login, state }: { login: string; state: "requested" | "approved" | "changes" }) {
  const [icon, label] = REVIEW_ICON[state];
  return <PersonChip login={login} title={`${login}: ${label}`}><span className="font-bold">{icon}</span></PersonChip>;
}

export function ReviewerChips({ pr }: { pr: GhPr }) {
  if (!pr.reviewers?.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1 pl-4" aria-label="revisores">
      {pr.reviewers.map((r) => <ReviewerChip key={r.login} login={r.login} state={r.state} />)}
    </div>
  );
}

function OpenPrButton({ pr }: { pr: GhPr }) {
  return (
    <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} title="Abrir en GitHub" asChild>
      <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
    </QueueItemAction>
  );
}

/** PR de GitHub sin sesión. Click = seleccionarla (o abrirla, según la sección); botones en hover.
 *  `showAuthor`: en Revisiones (de quién es); `showReviewers`: en Mis PRs (quién la revisa). */
/** `devKey`: la PR es un desarrollo (Mis desarrollos): su título se puede renombrar. `extraActions`:
 *  más acciones de hover (p.ej. ocultar). */
export function PrCard({ pr, reviewable = false, openOnClick = false, merge, showAuthor = false, showReviewers = false, devKey, extraActions, dev }:
  { pr: GhPr; reviewable?: boolean; openOnClick?: boolean; merge?: { job?: MergeJob; above: number };
    showAuthor?: boolean; showReviewers?: boolean; devKey?: string; extraActions?: React.ReactNode; dev?: DevStateInfo | null }) {
  const active = useFolders((s) => s.activePrUrl === pr.url);
  const setActivePr = useFolders((s) => s.setActivePr);
  const tone = devTone(pr, merge?.job);
  return (
    <QueueItem className="px-2 py-1">
      <CardShell tone={tone} dev={dev} selected={active} dashed
        onClick={() => { setActivePr(pr.url); if (openOnClick) window.open(pr.url, "_blank", "noopener"); }}>
        <CardCorner><DepsPause pr={pr} /><CiMark pr={pr} /></CardCorner>
        <div className={cn("flex items-start gap-1.5", titlePad(pr))}>
          <DevTitle devKey={devKey} prs={[pr]} original={pr.title} />
          <CardActions>
            {devKey && <RenameAction devKey={devKey} />}
            <StateAction dev={dev} devKey={devKey} />
            {reviewable && <ReviewButton pr={pr} />}
            {reviewable && <ReviewVerdictActions pr={pr} />}
            {extraActions}
            {merge && canMerge(pr) && !(merge.job && MERGE_ACTIVE.includes(merge.job.state))
              && merge.job?.state !== "done" && <MergeButton pr={pr} above={merge.above} />}
            {merge?.job?.state === "done" && (
              <QueueItemAction aria-label={`Archivar ${pr.repo}#${pr.number}`} title="Archivar (sacarla de la lista; no toca GitHub)"
                onClick={(e) => { e.stopPropagation(); dismissMerge(getWs(), pr.url).catch(() => {}); }}>
                <Archive size={11} />
              </QueueItemAction>)}
            <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} title="Abrir en GitHub" asChild>
              <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
            </QueueItemAction>
          </CardActions>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {devKey && <DevIndex devKey={devKey} prs={[pr]} />}
          <RefChip repo={pr.repo} number={pr.number} />
          {devKey && <LaterChip devKey={devKey} prs={[pr]} />}
          {showAuthor && <PersonChip login={pr.author} title={`autor: ${pr.author}`} />}
        </div>
        <CardMeta>
          {dev && <DevStateLabel dev={dev} devKey={devKey} />}
          {pr.draft && <span>draft</span>}
          {pr.stack && <span title="posición en el stack (1 = la de abajo)">◫ {pr.stack.position}/{pr.stack.size}</span>}
          {merge && <MergeStatus url={pr.url} job={merge.job} />}
          {showReviewers && pr.reviewers?.map((r) => <ReviewerChip key={r.login} login={r.login} state={r.state} />)}
        </CardMeta>
      </CardShell>
    </QueueItem>
  );
}

/** Línea de detalle chica; no ocupa espacio si no hay nada que mostrar. */
export function CardMeta({ children }: { children: React.ReactNode }) {
  const items = (Array.isArray(children) ? children.flat() : [children]).filter((c) => c !== null && c !== undefined && c !== false);
  if (items.length === 0) return null;
  return <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">{children}</div>;
}

function PrList({ prs, byId, reviewable }: { prs: GhPr[]; byId: Map<string, FolderSession>; reviewable: boolean }) {
  return (
    <QueueList>
      {prs.map((pr) => {
        const s = byId.get(pr.sessionId);
        // pendientes de revisar: solo revisar y abrir en GitHub (sin parar/archivar)
        return s ? <SessionItem key={pr.url} session={s} pr={pr} onlyActions={reviewable}
          actions={reviewable ? <><ReviewButton pr={pr} /><OpenPrButton pr={pr} /></> : null} />
          : <PrCard key={pr.url} pr={pr} reviewable={reviewable} showAuthor devKey={`p:${pr.url}`} />;
      })}
    </QueueList>
  );
}

/** Revisores visibles en los chips de Revisiones (miembros de la org, con checkbox). */
export function ReviewersPicker({ gh }: { gh: GithubReviews | null }) {
  const [error, setError] = useState<string | null>(null);
  const members = gh?.members ?? [];
  const selected = new Set(gh?.selected ?? gh?.reviewers.map((r) => r.login) ?? []);
  const toggle = (login: string) => {
    const next = new Set(selected);
    if (next.has(login)) next.delete(login); else next.add(login);
    setError(null);
    setReviewers(getWs(), [...next]).catch((e: any) => setError(e?.message ?? String(e)));
  };
  return (
    <div>
      {members.length === 0 && <p className="py-1 text-xs text-muted-foreground">
        {gh?.error ? `no se pudo leer la org: ${gh.error}` : "cargando miembros…"}</p>}
      {members.map((m) => (
        <label key={m.login} title={`Mostrar a ${m.login} en los chips de Revisiones`}
          className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-accent">
          <input type="checkbox" className="accent-primary" checked={selected.has(m.login)} onChange={() => toggle(m.login)} />
          <PersonChip login={m.login} />
          {m.name && <span className="truncate text-muted-foreground">{m.name}</span>}
        </label>))}
      {error && <p role="alert" className="py-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

/** Las PRs de una revisión de varias: sacar una (queda como revisión aparte) o moverla a otra revisión. */
function ReviewPrsAction({ session, prs }: { session: FolderSession; prs: GhPr[] }) {
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const out = (pr: GhPr) => {
    setErr(null);
    unlinkPr(getWs(), session.id, pr.url).then(() => setOpen(false)).catch((e: any) => setErr(e?.message ?? String(e)));
  };
  return (<>
    <QueueItemAction aria-label="PRs de esta revisión" title="Ver las PRs de esta revisión: sacar una o moverla a otra revisión (no toca GitHub)"
      onClick={(e) => { e.stopPropagation(); setOpen(true); }}><ArrowRightLeft size={11} /></QueueItemAction>
    {open && (
      <Dialog open onOpenChange={(o) => { if (!o) setOpen(false); }}>
        <DialogContent onClick={(e) => e.stopPropagation()} className="max-w-md">
          <DialogHeader><DialogTitle className="text-sm">PRs de esta revisión</DialogTitle></DialogHeader>
          <div className="space-y-0.5">
            {prs.map((p) => (
              <div key={p.url} className="flex items-center gap-1.5 rounded px-2 py-1 text-xs hover:bg-accent/50">
                <span className="shrink-0 font-mono font-bold">{p.repo}#{p.number}</span>
                <span className="min-w-0 flex-1 truncate">{p.title}</span>
                <MovePrAction pr={p} from={session.id} to="review" />
                <QueueItemAction aria-label={`Sacar ${p.repo}#${p.number} de esta revisión`} disabled={prs.length < 2}
                  title={prs.length < 2 ? "Es la única PR de la revisión" : "Sacarla de esta revisión: queda como revisión aparte"}
                  onClick={(e) => { e.stopPropagation(); out(p); }}><Unlink size={11} /></QueueItemAction>
              </div>))}
          </div>
          {err && <p role="alert" className="text-xs text-destructive">⚠ {err}</p>}
        </DialogContent>
      </Dialog>)}
  </>);
}

export function ReviewsSection({ sessions }: { sessions: FolderSession[] }) {
  const openModal = useFolders((s) => s.openModal);
  const { gh, error } = useGithubReviews();

  const byId = new Map(sessions.map((s) => [s.id, s]));
  const prBySession = new Map((gh ? allPrs(gh) : []).map((p) => [p.sessionId, p]));
  const ghError = error ?? gh?.error;
  const counts = new Map((gh?.reviewers ?? []).map((r) => [r.login, r.count]));
  const chips = gh?.selected
    ? gh.selected.map((login) => ({ login, count: counts.get(login) ?? 0 })).sort((a, b) => b.count - a.count)
    : gh?.reviewers ?? [];

  // revisión de stack: cada PR que incluye apunta a esa sesión
  const stackSession = new Map(sessions.flatMap((s) => (s.stackPrs ?? []).map((u) => [u, s] as const)));
  // stacks con 2+ PRs pendientes: "Revisar stack" (de abajo hacia arriba)
  const pendingByStack = new Map<string, GhPr[]>();
  for (const pr of gh?.pending ?? []) if (pr.stack) pendingByStack.set(pr.stack.id, [...(pendingByStack.get(pr.stack.id) ?? []), pr]);
  const stackOf = (pr: GhPr) => {
    const l = pr.stack ? pendingByStack.get(pr.stack.id) ?? [] : [];
    return l.length > 1 && !stackSession.has(pr.url) ? [...l].sort((a, b) => a.stack!.position - b.stack!.position) : null;
  };
  // una entrada por PR (con su sesión si la tiene) + las sesiones de revisión que no están en GitHub
  const prEntry = (pr: GhPr, status: string, reviewable: boolean): Entry => {
    const s = stackSession.get(pr.url) ?? byId.get(pr.sessionId);
    const stack = reviewable ? stackOf(pr) : null;
    return { key: pr.url, pr, session: s, status, render: () => s
      // pendientes de revisar: solo revisar y abrir en GitHub (sin parar/archivar)
      ? <SessionItem session={s} pr={pr} onlyActions={reviewable} noArchive={status === "changes"}
          actions={reviewable ? <>{!s.stackPrs && <ReviewButton pr={pr} />}{stack && <StackReviewButton prs={stack} />}<ReviewVerdictActions pr={pr} /><OpenPrButton pr={pr} /></>
            : <ReviewVerdictActions pr={pr} />} />
      : <PrCard pr={pr} reviewable={reviewable} showAuthor devKey={`p:${pr.url}`}
          extraActions={<>{reviewable ? (stack ? <StackReviewButton prs={stack} /> : undefined) : <ReviewVerdictActions pr={pr} />}
            <MovePrAction pr={pr} to="review" /></>} /> };
  };
  // las PRs de una revisión de stack van juntas en UNA card (la de la sesión), de abajo hacia arriba
  const listed = [...(gh?.pending ?? []).map((pr) => [pr, "pending"] as const),
    ...(gh?.changesRequested ?? []).map((pr) => [pr, "changes"] as const)];
  const stackEntries = new Map<string, Entry>();
  for (const [pr, status] of listed) {
    const s = stackSession.get(pr.url);
    if (!s || stackEntries.has(s.id)) continue;
    // de abajo hacia arriba; las que se movieron ahí de otro repo, al final
    const home = s.repos[0]?.name;
    const prs = listed.map(([p]) => p).filter((p) => s.stackPrs!.includes(p.url))
      .sort((a, b) => Number(a.repo !== home) - Number(b.repo !== home) || (a.stack?.position ?? 0) - (b.stack?.position ?? 0));
    stackEntries.set(s.id, { key: s.id, pr: prs[0], session: s, status,
      render: () => <SessionItem session={s} prs={prs} onlyActions actions={<ReviewPrsAction session={s} prs={prs} />} /> });
  }
  const entries: Entry[] = [
    ...listed.filter(([pr]) => !stackSession.has(pr.url)).map(([pr, status]) => prEntry(pr, status, status === "pending")),
    ...stackEntries.values(),
  ];
  const onGithub = new Set(entries.flatMap((e) => [e.pr!.sessionId, ...(e.session ? [e.session.id] : [])]));
  // las que no están pendientes ni con cambios pedidos: mergeadas/cerradas, aprobadas por mí o el resto
  const groupOf = (s: FolderSession, pr?: GhPr) => {
    if (s.prState === "merged" || s.prState === "closed") return "closed";
    const mine = pr?.reviewers?.find((r) => r.login === gh?.me);
    if (mine ? mine.state === "approved" : s.status === "approved") return "approved";
    if (mine ? mine.state === "changes" : s.status === "changes-requested") return "changes";
    // una revisión que abriste tú (sin que GitHub te la pida) y todavía no publicas: pendiente
    if (s.status === "reviewing") return "pending";
    return "others";
  };
  for (const s of sessions.filter((x) => !onGithub.has(x.id))) {
    const pr = prBySession.get(s.id);
    entries.push({ key: s.id, pr, session: s, status: groupOf(s, pr), render: () => <SessionItem session={s} pr={pr} /> });
  }

  return (
    <GroupedSection id="reviews" title="Revisiones" entries={waitingFirst(entries)} gh={gh}
      count={entries.filter((e) => e.status === "pending").length} countTitle="pendientes de tu review"
      groupActions={{ closed: <ArchiveClosed sessions={entries.filter((e) => e.status === "closed" && e.session).map((e) => e.session!)} /> }}
      statuses={[["pending", "Pendientes"], ["changes", "Pedí cambios"], ["approved", "Aprobé"],
                 ["closed", "Cerradas"], ["others", "Otras"]]}
      status={<>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        <SyncWarning gh={gh} />
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
      </>}
      headerExtra={<>
        <button aria-label="Nueva revisión" title="Nueva revisión" onClick={() => openModal("review")}
          className="grid h-5 w-5 place-items-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"><Plus size={13} /></button>
      </>}
      beforeGroups={chips.length > 0 && (
        <div className="mx-2.5 mt-1.5 flex flex-wrap gap-1" aria-label="Revisiones pendientes por revisor">
          {chips.map((r) => (
            <PersonChip key={r.login} login={r.login} strong={r.login === gh!.me}
              title={`${r.login}: ${r.count} revisiones pendientes${gh!.reviewersTruncated ? " (o más: GitHub corta la búsqueda en 1000 PRs)" : ""}`}>
              <span className="text-foreground">{r.count}{gh!.reviewersTruncated ? "+" : ""}</span>
            </PersonChip>))}
        </div>)} />
  );
}
