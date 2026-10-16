// ui/src/modules/sessions/SessionItem.tsx
import { useState, type ReactNode } from "react";
import { Archive, ExternalLink, Square } from "lucide-react";
import type { FolderSession, GhPr } from "../../transport/folderSessions";
import { CardMeta, CiMark } from "./ReviewsSection";
import { CardShell, DepsPause, DevTitle, RefChip, devTone, repoShort } from "./DevCard";
import { byRepoStack, worstPr } from "./desarrollos";
import { PersonChip } from "../../lib/people";
import { stopSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
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

/** `prs`: las PRs del desarrollo de la sesión (Mis desarrollos); con más de una se muestran como filas. */
/** `noArchive`: sin botón archivar (p.ej. revisiones donde pediste cambios: siguen vivas). */
export function SessionItem({ session, actions, pr: prProp, prs, onlyActions = false, noArchive = false }:
  { session: FolderSession; actions?: ReactNode; pr?: GhPr; prs?: GhPr[]; onlyActions?: boolean; noArchive?: boolean }) {
  const pr = prProp ?? prs?.[0];
  const many = (prs?.length ?? 0) > 1;
  const { activeId, activePrUrl, setActive } = useFolders();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dot, label] = DOT[session.process];
  // varias PRs (stack o fullstack): el tono y el CI los da la peor
  const worst = many ? worstPr(prs!) : { review: pr, ci: pr };
  const tone = devTone(worst.review, undefined, { merged: session.prState === "merged", status: session.status });
  const groups = many ? byRepoStack(prs!) : [];
  const repos = [...new Set([...session.repos.map((r) => r.name), ...(prs ?? []).map((p) => p.repo)])].sort();
  const isReview = session.kind === "review";
  return (
    <QueueItem className="px-2 py-1">
      {/* con una PR (sin sesión) elegida, la sesión anterior ya no es el desarrollo activo */}
      <CardShell tone={tone} onClick={() => setActive(session.id)}
        selected={activeId === session.id && !activePrUrl || !!prs?.some((p) => p.url === activePrUrl)}>
        <div className="flex items-start gap-1.5">
          <span aria-label={label} title={`claude ${label}`}
            className={cn(session.process === "running" ? "text-primary" : "text-muted-foreground")}>{dot}</span>
          <DevTitle devKey={`s:${session.id}`} prs={prs ?? (pr ? [pr] : [])}
            original={session.title ?? pr?.title ?? prLabel(session.prUrl) ?? session.id} />
          <DepsPause pr={pr} />
          {worst.ci && <CiMark pr={worst.ci} />}
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
            {!onlyActions && !noArchive && (
              <QueueItemAction aria-label={`Archivar ${session.id}`} title="Archivar"
                onClick={(e) => { e.stopPropagation(); setConfirm(true); }}>
                <Archive size={11} />
              </QueueItemAction>)}
          </QueueItemActions>
        </div>
        {/* repos con su número: una chip por PR (con varias, por repo: las filas dan los números) */}
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {many ? groups.flatMap((g) => g.stacks.flat()).map((p) => <RefChip key={p.url} repo={p.repo} number={p.number} pr={p} />)
            : pr ? <RefChip repo={pr.repo} number={pr.number} pr={pr} />
            : prLabel(session.prUrl) ? <span className="rounded border border-border px-1 font-mono text-[10px] font-bold">{prLabel(session.prUrl)}</span>
            : repos.length ? repos.map((r) => <RefChip key={r} repo={r} />)
            : <span className="font-mono text-[10px] text-muted-foreground">{session.id}</span>}
          {isReview && session.meta.author && <PersonChip login={session.meta.author} title={`autor: ${session.meta.author}`} />}
        </div>
        <CardMeta>
          {!many && pr?.stack && <span title="posición en el stack (1 = la de abajo)">◫ {pr.stack.position}/{pr.stack.size}</span>}
          {session.prState === "stale" && <span className="text-sky-400"
            title="El PR tiene commits nuevos desde tu revisión: abre la sesión y toca Refrescar">⟳ commits nuevos desde tu revisión</span>}
          {session.prState === "closed" && <span>PR cerrada</span>}
          {session.pollError && <span className="text-destructive"
            title={`${session.pollError} (último OK: ${session.lastOk ?? "nunca"})`}>⚠ no se pudo consultar el PR</span>}
          {session.attention === "trust" && <span className="text-destructive"
            title="Claude Code pide confirmar la carpeta: abre la terminal y acepta">⚠ confiar carpeta</span>}
          {/* el detalle de los worktrees está en el módulo Desarrollo */}
          {session.repos.some((r) => r.state === "missing") && <span className="text-destructive"
            title="Falta el worktree de algún repo: míralo en el módulo Desarrollo">⚠ falta un worktree</span>}
          {session.repos.some((r) => r.setup === "failed") && <span className="text-destructive"
            title="Falló el setup de algún repo: míralo en el módulo Desarrollo">✗ setup</span>}
        </CardMeta>
      </CardShell>
      <ConfirmArchiveDialog id={session.id} open={confirm} onClose={() => setConfirm(false)} />
    </QueueItem>
  );
}
