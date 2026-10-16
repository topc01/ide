// ui/src/modules/sessions/SessionItem.tsx
import { useState, type ReactNode } from "react";
import { Archive, Square } from "lucide-react";
import type { FolderSession, GhPr } from "../../transport/folderSessions";
import { CiMark, DepsBadge, StackBadge } from "./ReviewsSection";
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
export function SessionItem({ session, actions, pr, onlyActions = false }:
  { session: FolderSession; actions?: ReactNode; pr?: GhPr; onlyActions?: boolean }) {
  const { activeId, setActive } = useFolders();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dot, label] = DOT[session.process];
  const extra = session.pollError ? "⚠ poll" : session.prState;
  return (
    <QueueItem className="px-2 py-0.5">
      <div onClick={() => setActive(session.id)}
        aria-current={activeId === session.id || undefined}
        className={cn("cursor-pointer rounded-md border border-border bg-background/40 px-2 py-1.5 text-xs hover:bg-accent/60",
          activeId === session.id && "border-primary bg-accent text-foreground")}>
        <div className="flex items-center gap-1.5">
          <span aria-label={label} className={cn(session.process === "running" ? "text-primary" : "text-muted-foreground")}>{dot}</span>
          <span className="min-w-0 flex-1 truncate" title={session.title ?? session.id}>{session.title ?? session.id}</span>
          {(session.error || session.launchError) && (
            <span title={session.error ?? session.launchError ?? ""} className="text-destructive">⚠</span>)}
          {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
          <QueueItemActions className="ml-0">
            {actions}
            {!onlyActions && session.process !== "stopped" && (
              <QueueItemAction aria-label={`Parar ${session.id}`}
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
        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 pl-4 text-[10px] text-muted-foreground">
          {session.title && <span className="font-mono">{session.id}</span>}
          {session.meta.author && <span>{session.meta.author}</span>}
          {pr && <StackBadge pr={pr} />}
          {pr && <DepsBadge pr={pr} />}
          {pr && <CiMark pr={pr} />}
          {session.status && <Badge variant="outline" className="px-1 py-0 text-[10px]">{session.status}</Badge>}
          {extra && <Badge variant={session.pollError ? "destructive" : "secondary"} className="px-1 py-0 text-[10px]"
            title={session.pollError
              ? `${session.pollError} (último OK: ${session.lastOk ?? "nunca"})` : undefined}>{extra}</Badge>}
          {session.attention === "trust" && <Badge variant="destructive" className="px-1 py-0 text-[10px]"
            title="Claude Code pide confirmar la carpeta: abre la terminal y acepta">⚠ confiar carpeta</Badge>}
        </div>
        {session.repos.map((r) => <RepoLine key={r.name} session={session} repo={r} />)}
      </div>
      <ConfirmArchiveDialog id={session.id} open={confirm} onClose={() => setConfirm(false)} />
    </QueueItem>
  );
}
