// ui/src/modules/sessions/SessionItem.tsx
import { useState, type ReactNode } from "react";
import { Archive, ExternalLink, Square } from "lucide-react";
import type { FolderSession, GhPr } from "../../transport/folderSessions";
import { CardMeta } from "./ReviewsSection";
import { CardShell, DepsPause, devTone, repoShort } from "./DevCard";
import { PersonChip } from "../../lib/people";
import { stopSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { RepoLine } from "./RepoLine";
import { ConfirmArchiveDialog } from "./ConfirmArchiveDialog";
import { cn } from "../../lib/utils";

const DOT = { running: ["●", "corriendo"], stopped: ["○", "parada"], queued: ["◌", "en cola"] } as const;

/** `pr`: la PR de GitHub de la sesión (si se conoce): agrega su posición en el stack.
 *  `onlyActions`: el hover muestra solo `actions` (sin parar/archivar). */
/** "https://github.com/o/finnecto-api/pull/4581" → "API #4581" (PR ya cerrada: sin datos de GitHub). */
function prLabel(url?: string | null): string | null {
  const m = url?.match(/github\.com\/[^/]+\/([^/]+)\/pull\/(\d+)/);
  return m ? `${repoShort(m[1])} #${m[2]}` : null;
}

export function SessionItem({ session, actions, pr, onlyActions = false }:
  { session: FolderSession; actions?: ReactNode; pr?: GhPr; onlyActions?: boolean }) {
  const { activeId, activePrUrl, setActive } = useFolders();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dot, label] = DOT[session.process];
  const tone = devTone(pr, undefined, { merged: session.prState === "merged", status: session.status });
  const isReview = session.kind === "review";
  return (
    <QueueItem className="px-2 py-1">
      {/* con una PR (sin sesión) elegida, la sesión anterior ya no es el desarrollo activo */}
      <CardShell tone={tone} selected={activeId === session.id && !activePrUrl} onClick={() => setActive(session.id)}>
        <div className="flex items-center gap-1.5">
          <span aria-label={label} title={`claude ${label}`}
            className={cn(session.process === "running" ? "text-primary" : "text-muted-foreground")}>{dot}</span>
          <span className="font-mono text-[11px] font-bold tracking-wide">
            {pr ? `${repoShort(pr.repo)} #${pr.number}` : prLabel(session.prUrl) ?? session.id}</span>
          {isReview && session.meta.author && <PersonChip login={session.meta.author} title={`autor: ${session.meta.author}`} />}
          <span className="flex-1" />
          <DepsPause pr={pr} />
          {(session.error || session.launchError) && (
            <span title={session.error ?? session.launchError ?? ""} className="text-destructive">⚠</span>)}
          {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
          <QueueItemActions className="ml-0">
            {actions}
            {/* toda card con PR se puede abrir en GitHub (las pendientes ya lo traen en `actions`) */}
            {!onlyActions && (pr?.url ?? session.prUrl) && (
              <QueueItemAction aria-label={`Abrir ${session.id} en GitHub`} title="Abrir la PR en GitHub" asChild>
                <a href={pr?.url ?? session.prUrl ?? ""} target="_blank" rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
              </QueueItemAction>)}
            {!onlyActions && session.process !== "stopped" && (
              <QueueItemAction aria-label={`Parar ${session.id}`} title="Parar el claude de esta sesión"
                onClick={(e) => {
                  e.stopPropagation();
                  setError(null);
                  stopSession(getWs(), session.id).catch((err: any) => setError(err?.message ?? String(err)));
                }}>
                <Square size={11} />
              </QueueItemAction>)}
            {!onlyActions && (
              <QueueItemAction aria-label={`Archivar ${session.id}`} title="Archivar"
                onClick={(e) => { e.stopPropagation(); setConfirm(true); }}>
                <Archive size={11} />
              </QueueItemAction>)}
          </QueueItemActions>
        </div>
        <div className="mt-0.5 line-clamp-2 leading-snug" title={session.title ?? session.id}>{session.title ?? session.id}</div>
        <CardMeta>
          {pr?.stack && <span title="posición en el stack (1 = la de abajo)">◫ {pr.stack.position}/{pr.stack.size}</span>}
          {session.prState === "stale" && <span className="text-sky-400"
            title="El PR tiene commits nuevos desde tu revisión: abre la sesión y toca Refrescar">⟳ commits nuevos desde tu revisión</span>}
          {session.prState === "closed" && <span>PR cerrada</span>}
          {session.pollError && <span className="text-destructive"
            title={`${session.pollError} (último OK: ${session.lastOk ?? "nunca"})`}>⚠ no se pudo consultar el PR</span>}
          {session.attention === "trust" && <span className="text-destructive"
            title="Claude Code pide confirmar la carpeta: abre la terminal y acepta">⚠ confiar carpeta</span>}
        </CardMeta>
        {/* el worktree solo importa en tickets (rama propia y scripts); en revisiones está en detach */}
        {!isReview && session.repos.map((r) => <RepoLine key={r.name} session={session} repo={r} />)}
      </CardShell>
      <ConfirmArchiveDialog id={session.id} open={confirm} onClose={() => setConfirm(false)} />
    </QueueItem>
  );
}
