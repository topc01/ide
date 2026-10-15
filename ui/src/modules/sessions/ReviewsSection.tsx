// ui/src/modules/sessions/ReviewsSection.tsx
import { useEffect, useState } from "react";
import { ExternalLink, Plus, ScanEye } from "lucide-react";
import { useFolders } from "../../state/folders";
import {
  fetchGithubReviews, onGithubReviews, startReview, type FolderSession, type GhPr, type GithubReviews,
} from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { Queue, QueueSection, QueueSectionTrigger, QueueSectionLabel, QueueSectionContent, QueueList,
  QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
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

  return (<>
    <div className="mx-2.5 mt-3 flex items-center gap-1.5 border-t border-border pt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
      <span>Revisiones</span>
      {ghError && <span role="alert" className="normal-case text-destructive"
        title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
      {!gh && !ghError && <span className="normal-case">cargando…</span>}
      <button aria-label="Nueva revisión" onClick={() => openModal("review")}
        className="ml-auto hover:text-foreground"><Plus size={12} /></button>
    </div>
    {gh && gh.reviewers.length > 0 && (
      <div className="mx-2.5 mt-1.5 flex flex-wrap gap-1"
        aria-label="Revisiones pendientes por revisor">
        {gh.reviewers.map((r) => (
          <span key={r.login} title={`${r.count} revisiones pendientes${gh.reviewersTruncated ? " (o más: solo se miran 100 PRs)" : ""}`}
            className={cn("flex items-center gap-1 rounded-full border px-1.5 py-px font-mono text-[10px]",
              r.login === gh.me ? "border-primary text-primary" : "border-border text-muted-foreground")}>
            {r.login}<span className="text-foreground">{r.count}{gh.reviewersTruncated ? "+" : ""}</span>
          </span>))}
      </div>)}
    <Queue>
      <QueueSection defaultOpen>
        <QueueSectionTrigger><QueueSectionLabel label="Pendientes" count={gh?.pending.length ?? 0} /></QueueSectionTrigger>
        <QueueSectionContent><PrList prs={gh?.pending ?? []} byId={byId} reviewable /></QueueSectionContent>
      </QueueSection>
      <QueueSection defaultOpen>
        <QueueSectionTrigger><QueueSectionLabel label="Pedí cambios" count={gh?.changesRequested.length ?? 0} /></QueueSectionTrigger>
        <QueueSectionContent><PrList prs={gh?.changesRequested ?? []} byId={byId} reviewable={false} /></QueueSectionContent>
      </QueueSection>
      {others.length > 0 && (
        <QueueSection defaultOpen>
          <QueueSectionTrigger><QueueSectionLabel label="Otras" count={others.length} /></QueueSectionTrigger>
          <QueueSectionContent>
            <QueueList>{others.map((s) => <SessionItem key={s.id} session={s} />)}</QueueList>
          </QueueSectionContent>
        </QueueSection>)}
    </Queue>
  </>);
}
