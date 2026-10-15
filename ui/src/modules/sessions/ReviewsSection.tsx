// ui/src/modules/sessions/ReviewsSection.tsx
import { useEffect, useState } from "react";
import { ChevronRight, ExternalLink, MoreHorizontal, Plus, ScanEye } from "lucide-react";
import { Collapsible } from "radix-ui";
import { useFolders } from "../../state/folders";
import {
  fetchGithubReviews, onGithubReviews, setReviewers, startReview, type FolderSession, type GhPr, type GithubReviews,
} from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { QueueList, QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { SessionItem } from "./SessionItem";
import { cn } from "../../lib/utils";

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

/** PR de GitHub que todavía no tiene sesión. */
function PrCard({ pr, reviewable }: { pr: GhPr; reviewable: boolean }) {
  return (
    <QueueItem>
      <div className="flex items-center gap-1.5 border-l-2 border-transparent px-2 py-1 text-xs hover:bg-accent/60">
        <span className="text-muted-foreground" aria-label="sin sesión">◇</span>
        <span className="font-mono text-[11px]">{pr.repo.replace(/^finnecto-/, "")}#{pr.number}</span>
        <span className="truncate text-muted-foreground" title={pr.title}>{pr.title}</span>
        <span className="text-[10px] text-muted-foreground">{pr.author}</span>
        {pr.draft && <Badge variant="outline">draft</Badge>}
        <QueueItemActions>
          {reviewable && <ReviewButton pr={pr} />}
          <QueueItemAction aria-label={`Abrir ${pr.sessionId} en GitHub`} asChild>
            <a href={pr.url} target="_blank" rel="noreferrer"><ExternalLink size={11} /></a>
          </QueueItemAction>
        </QueueItemActions>
      </div>
    </QueueItem>
  );
}

function PrList({ prs, byId, reviewable }: { prs: GhPr[]; byId: Map<string, FolderSession>; reviewable: boolean }) {
  return (
    <QueueList>
      {prs.map((pr) => {
        const s = byId.get(pr.sessionId);
        return s ? <SessionItem key={pr.url} session={s} actions={reviewable ? <ReviewButton pr={pr} /> : null} />
          : <PrCard key={pr.url} pr={pr} reviewable={reviewable} />;
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
      <button aria-label="Configurar revisiones" aria-expanded={open} onClick={() => setOpen((o) => !o)}
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

function Group({ label, count, children }: { label: string; count: number; children: React.ReactNode }) {
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
  const [gh, setGh] = useState<GithubReviews | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ws = getWs();
    fetchGithubReviews(ws).then(setGh).catch((e: any) => setError(e?.message ?? String(e)));
    return onGithubReviews(ws, (r) => { setGh(r); setError(null); });
  }, []);

  const byId = new Map(sessions.map((s) => [s.id, s]));
  const onGithub = new Set([...(gh?.pending ?? []), ...(gh?.changesRequested ?? [])].map((p) => p.sessionId));
  const others = sessions.filter((s) => !onGithub.has(s.id));
  const ghError = error ?? gh?.error;
  const counts = new Map((gh?.reviewers ?? []).map((r) => [r.login, r.count]));
  const chips = gh?.selected
    ? gh.selected.map((login) => ({ login, count: counts.get(login) ?? 0 })).sort((a, b) => b.count - a.count)
    : gh?.reviewers ?? [];

  return (
    <Collapsible.Root defaultOpen className="group/reviews mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
          <ChevronRight size={13} className="transition-transform group-data-[state=open]/reviews:rotate-90" />
          Revisiones
        </Collapsible.Trigger>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
        <div className="ml-auto flex items-center gap-1">
          <ReviewersMenu gh={gh} />
          <button aria-label="Nueva revisión" onClick={() => openModal("review")}
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
            <QueueList>{others.map((s) => <SessionItem key={s.id} session={s} />)}</QueueList>
          </Group>)}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
