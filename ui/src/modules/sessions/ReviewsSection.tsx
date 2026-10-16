// ui/src/modules/sessions/ReviewsSection.tsx
import { useEffect, useState } from "react";
import { Archive, Check, ChevronRight, ExternalLink, Layers2, Link2, Loader2, MoreHorizontal, Plus, ScanEye, X } from "lucide-react";
import { Collapsible } from "radix-ui";
import { useFolders } from "../../state/folders";
import {
  dismissMerge, fetchGithubReviews, onGithubReviews, setReviewers, startReview, type MergeJob, type FolderSession, type GhPr, type GithubReviews,
} from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { QueueList, QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { SessionItem } from "./SessionItem";
import { GroupedSection, type Entry } from "./GroupedSection";
import { canMerge, MERGE_ACTIVE, MergeButton, MergeStatus } from "./MergeControls";
import { CardShell, DepsPause, DevTitle, devTone, repoShort } from "./DevCard";
import { cn } from "../../lib/utils";
import { PersonChip } from "../../lib/people";
import { usePersistentOpen } from "../../lib/persist";

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
  requested: ["border-sky-500/60 text-sky-400", "review pedida"],
  approved: ["border-emerald-500/60 text-emerald-400", "aprobó"],
  changes: ["border-amber-400/60 text-amber-300", "pidió cambios"],
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
  if (!pr.ci) return null;
  // marca de esquina (como el ⏸): ✓ verde pasó · ✗ roja falló/conflicto · ⟳ amarilla corriendo
  const [Icon, cls, label] = pr.ci === "success" ? [Check, "bg-emerald-500/15 text-emerald-400", "CI pasó"]
    : pr.ci === "pending" ? [Loader2, "bg-amber-400/15 text-amber-300", "CI corriendo"]
    : [X, "bg-red-500/20 text-red-500", pr.conflict ? "conflicto con la base" : "CI falló"];
  return (
    <span aria-label={label} title={label} className={cn("grid h-[18px] w-[18px] shrink-0 place-items-center rounded", cls)}>
      <Icon size={12} strokeWidth={3} className={pr.ci === "pending" ? "animate-spin" : undefined} />
    </span>
  );
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
/** `devKey`: la PR es un desarrollo (Mis desarrollos): su título se puede renombrar. */
export function PrCard({ pr, reviewable = false, openOnClick = false, merge, showAuthor = false, showReviewers = false, devKey }:
  { pr: GhPr; reviewable?: boolean; openOnClick?: boolean; merge?: { job?: MergeJob; above: number };
    showAuthor?: boolean; showReviewers?: boolean; devKey?: string }) {
  const active = useFolders((s) => s.activePrUrl === pr.url);
  const setActivePr = useFolders((s) => s.setActivePr);
  const tone = devTone(pr, merge?.job);
  return (
    <QueueItem className="px-2 py-1">
      <CardShell tone={tone} selected={active} dashed
        onClick={() => { setActivePr(pr.url); if (openOnClick) window.open(pr.url, "_blank", "noopener"); }}>
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[11px] font-bold tracking-wide">{repoShort(pr.repo)} #{pr.number}</span>
          {showAuthor && <PersonChip login={pr.author} title={`autor: ${pr.author}`} />}
          <span className="flex-1" />
          <DepsPause pr={pr} />
          <CiMark pr={pr} />
          <QueueItemActions className="ml-0">
            {reviewable && <ReviewButton pr={pr} />}
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
          </QueueItemActions>
        </div>
        {devKey ? <DevTitle devKey={devKey} prs={[pr]} original={pr.title} />
          : <div className="mt-0.5 line-clamp-2 leading-snug" title={pr.title}>{pr.title}</div>}
        <CardMeta>
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

  // una entrada por PR (con su sesión si la tiene) + las sesiones de revisión que no están en GitHub
  const prEntry = (pr: GhPr, status: string, reviewable: boolean): Entry => {
    const s = byId.get(pr.sessionId);
    return { key: pr.url, pr, session: s, status, render: () => s
      // pendientes de revisar: solo revisar y abrir en GitHub (sin parar/archivar)
      ? <SessionItem session={s} pr={pr} onlyActions={reviewable} noArchive={status === "changes"}
          actions={reviewable ? <><ReviewButton pr={pr} /><OpenPrButton pr={pr} /></> : null} />
      : <PrCard pr={pr} reviewable={reviewable} showAuthor devKey={`p:${pr.url}`} /> };
  };
  const entries: Entry[] = [
    ...(gh?.pending ?? []).map((pr) => prEntry(pr, "pending", true)),
    ...(gh?.changesRequested ?? []).map((pr) => prEntry(pr, "changes", false)),
  ];
  const onGithub = new Set(entries.map((e) => e.pr!.sessionId));
  // las que no están pendientes ni con cambios pedidos: mergeadas/cerradas, aprobadas por mí o el resto
  const groupOf = (s: FolderSession, pr?: GhPr) => {
    if (s.prState === "merged" || s.prState === "closed") return "closed";
    const mine = pr?.reviewers?.find((r) => r.login === gh?.me);
    if (mine ? mine.state === "approved" : s.status === "approved") return "approved";
    return "others";
  };
  for (const s of sessions.filter((x) => !onGithub.has(x.id))) {
    const pr = prBySession.get(s.id);
    entries.push({ key: s.id, pr, session: s, status: groupOf(s, pr), render: () => <SessionItem session={s} pr={pr} /> });
  }

  return (
    <GroupedSection id="reviews" title="Revisiones" entries={entries} gh={gh}
      statuses={[["pending", "Pendientes"], ["changes", "Pedí cambios"], ["approved", "Aprobé"],
                 ["closed", "Cerradas"], ["others", "Otras"]]}
      status={<>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
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
