// ui/src/modules/sessions/ReviewsSection.tsx
import { useEffect, useState } from "react";
import { ChevronRight, ExternalLink, Layers2, Link2, MoreHorizontal, Plus, ScanEye } from "lucide-react";
import { Collapsible } from "radix-ui";
import { useFolders } from "../../state/folders";
import {
  fetchGithubReviews, onGithubReviews, setReviewers, startReview, type MergeJob, type FolderSession, type GhPr, type GithubReviews,
} from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { QueueList, QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { SessionItem } from "./SessionItem";
import { canMerge, MERGE_ACTIVE, MergeButton, MergeStatus } from "./MergeControls";
import { CardShell, DepsLine, devTone, repoShort } from "./DevCard";
import { cn } from "../../lib/utils";
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
  const [mark, cls, label] = pr.ci === "success" ? ["✓", "text-emerald-400", "CI pasó"]
    : pr.ci === "pending" ? ["◌", "text-amber-300", "CI corriendo"]
    // rojo puro (no el `destructive` terracota del tema) y con fondo: tiene que saltar a la vista
    : ["✗", "rounded-sm bg-red-500/20 px-1 text-[12px] leading-4 text-red-500 ring-1 ring-red-500/60",
       pr.conflict ? "conflicto con la base" : "CI falló"];
  return <span aria-label={label} title={label} className={cn("shrink-0 font-mono font-bold", cls)}>{mark}</span>;
}

/** Quién revisa la PR, con el color de su estado. */
export function ReviewerChips({ pr }: { pr: GhPr }) {
  if (!pr.reviewers?.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1 pl-4" aria-label="revisores">
      {pr.reviewers.map((r) => {
        const [cls, label] = REVIEWER_TONE[r.state];
        return <span key={r.login} title={`${r.login}: ${label}`}
          className={cn("rounded-full border px-1.5 font-mono text-[10px]", cls)}>{r.login}</span>;
      })}
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

const REVIEWER_TEXT = { requested: "text-sky-400", approved: "text-emerald-400", changes: "text-amber-300" } as const;

/** PR de GitHub sin sesión. Click = seleccionarla (o abrirla, según la sección); botones en hover.
 *  `showAuthor`: en Revisiones (de quién es); `showReviewers`: en Mis PRs (quién la revisa). */
export function PrCard({ pr, reviewable = false, openOnClick = false, merge, showAuthor = false, showReviewers = false }:
  { pr: GhPr; reviewable?: boolean; openOnClick?: boolean; merge?: { job?: MergeJob; above: number };
    showAuthor?: boolean; showReviewers?: boolean }) {
  const active = useFolders((s) => s.activePrUrl === pr.url);
  const setActivePr = useFolders((s) => s.setActivePr);
  const tone = devTone(pr, merge?.job);
  return (
    <QueueItem className="px-2 py-1">
      <CardShell tone={tone} selected={active} dashed
        onClick={() => { setActivePr(pr.url); if (openOnClick) window.open(pr.url, "_blank", "noopener"); }}>
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[11px] font-bold tracking-wide">{repoShort(pr.repo)} #{pr.number}</span>
          {showAuthor && <span className="truncate text-[11px] text-foreground/80">{pr.author}</span>}
          <span className="flex-1" />
          <QueueItemActions className="ml-0">
            {reviewable && <ReviewButton pr={pr} />}
            {merge && canMerge(pr) && !(merge.job && MERGE_ACTIVE.includes(merge.job.state))
              && merge.job?.state !== "done" && <MergeButton pr={pr} above={merge.above} />}
            <QueueItemAction aria-label={`Abrir ${pr.repo}#${pr.number} en GitHub`} title="Abrir en GitHub" asChild>
              <a href={pr.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
            </QueueItemAction>
          </QueueItemActions>
        </div>
        <div className="mt-0.5 line-clamp-2 leading-snug" title={pr.title}>{pr.title}</div>
        <CardMeta>
          {pr.draft && <span>draft</span>}
          {pr.stack && <span title="posición en el stack (1 = la de abajo)">◫ {pr.stack.position}/{pr.stack.size}</span>}
          <DepsLine pr={pr} />
          {merge && <MergeStatus url={pr.url} job={merge.job} />}
          {showReviewers && pr.reviewers?.map((r) => (
            <span key={r.login} className={REVIEWER_TEXT[r.state]}
              title={`${r.login}: ${{ requested: "review pedida", approved: "aprobó", changes: "pidió cambios" }[r.state]}`}>
              {r.login}</span>))}
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
          : <PrCard key={pr.url} pr={pr} reviewable={reviewable} showAuthor />;
      })}
    </QueueList>
  );
}

/** Menú ⋯ de Revisiones: qué revisores (miembros de la org) se ven en los chips. */
function ReviewersMenu({ gh }: { gh: GithubReviews | null }) {
  const [open, setOpen] = useState(false);
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
    <div className="relative">
      <button aria-label="Configurar revisiones" title="Configurar revisiones" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="grid h-5 w-5 place-items-center rounded text-muted-foreground hover:text-foreground">
        <MoreHorizontal size={13} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-border bg-popover p-1 normal-case tracking-normal shadow">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">Revisores visibles</div>
          {members.length === 0 && <p className="px-2 py-1 text-xs text-muted-foreground">
            {gh?.error ? `no se pudo leer la org: ${gh.error}` : "cargando miembros…"}</p>}
          {members.map((m) => (
            <label key={m.login} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-accent">
              <input type="checkbox" className="accent-primary" checked={selected.has(m.login)}
                onChange={() => toggle(m.login)} />
              <span className="font-mono">{m.login}</span>
              {m.name && <span className="truncate text-muted-foreground">{m.name}</span>}
            </label>))}
          {error && <p role="alert" className="px-2 py-1 text-xs text-destructive">{error}</p>}
        </div>)}
    </div>
  );
}

export function Group({ label, count, children }: { label: string; count: number; children: React.ReactNode }) {
  return (
    <div className="mt-1">
      <div className="flex items-center px-2.5 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>{label}</span><span className="ml-auto font-mono text-primary">{count}</span>
      </div>
      {children}
    </div>
  );
}

export function ReviewsSection({ sessions }: { sessions: FolderSession[] }) {
  const openModal = useFolders((s) => s.openModal);
  const { gh, error } = useGithubReviews();
  const [open, setOpen] = usePersistentOpen("reviews");

  const byId = new Map(sessions.map((s) => [s.id, s]));
  const onGithub = new Set([...(gh?.pending ?? []), ...(gh?.changesRequested ?? [])].map((p) => p.sessionId));
  const others = sessions.filter((s) => !onGithub.has(s.id));
  const prBySession = new Map((gh ? allPrs(gh) : []).map((p) => [p.sessionId, p]));
  const ghError = error ?? gh?.error;
  const counts = new Map((gh?.reviewers ?? []).map((r) => [r.login, r.count]));
  const chips = gh?.selected
    ? gh.selected.map((login) => ({ login, count: counts.get(login) ?? 0 })).sort((a, b) => b.count - a.count)
    : gh?.reviewers ?? [];

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="group/reviews mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger title="Colapsar / expandir la sección" className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
          <ChevronRight size={13} className="transition-transform group-data-[state=open]/reviews:rotate-90" />
          Revisiones
        </Collapsible.Trigger>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
        <div className="ml-auto flex items-center gap-1">
          <ReviewersMenu gh={gh} />
          <button aria-label="Nueva revisión" title="Nueva revisión" onClick={() => openModal("review")}
            className="text-muted-foreground hover:text-foreground"><Plus size={13} /></button>
        </div>
      </div>
      <Collapsible.Content>
        {chips.length > 0 && (
          <div className="mx-2.5 mt-1.5 flex flex-wrap gap-1" aria-label="Revisiones pendientes por revisor">
            {chips.map((r) => (
              <span key={r.login} title={`${r.count} revisiones pendientes${gh!.reviewersTruncated ? " (o más: GitHub corta la búsqueda en 1000 PRs)" : ""}`}
                className={cn("flex items-center gap-1 rounded-full border px-1.5 py-px font-mono text-[10px]",
                  r.login === gh!.me ? "border-primary text-primary" : "border-border text-muted-foreground")}>
                {r.login}<span className="text-foreground">{r.count}{gh!.reviewersTruncated ? "+" : ""}</span>
              </span>))}
          </div>)}
        <Group label="Pendientes" count={gh?.pending.length ?? 0}>
          <PrList prs={gh?.pending ?? []} byId={byId} reviewable />
        </Group>
        <Group label="Pedí cambios" count={gh?.changesRequested.length ?? 0}>
          <PrList prs={gh?.changesRequested ?? []} byId={byId} reviewable={false} />
        </Group>
        {others.length > 0 && (
          <Group label="Otras" count={others.length}>
            <QueueList>{others.map((s) => <SessionItem key={s.id} session={s} pr={prBySession.get(s.id)} />)}</QueueList>
          </Group>)}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
