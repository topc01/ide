// ui/src/modules/sessions/SessionItem.tsx
import { useState } from "react";
import { Square, Trash2 } from "lucide-react";
import type { FolderSession } from "../../transport/folderSessions";
import { stopSession } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { RepoLine } from "./RepoLine";
import { ConfirmRmDialog } from "./ConfirmRmDialog";
import { cn } from "../../lib/utils";

const DOT = { running: ["●", "corriendo"], stopped: ["○", "parada"], queued: ["◌", "en cola"] } as const;

export function SessionItem({ session }: { session: FolderSession }) {
  const { activeId, setActive } = useFolders();
  const [confirm, setConfirm] = useState(false);
  const [dot, label] = DOT[session.process];
  const extra = session.pollError ? "⚠ poll" : session.prState;
  return (
    <QueueItem>
      <div onClick={() => setActive(session.id)}
        className={cn("flex cursor-pointer items-center gap-1.5 px-2.5 py-1 text-xs hover:bg-accent",
          activeId === session.id && "bg-accent")}>
        <span aria-label={label} className={cn(session.process === "running" ? "text-primary" : "text-muted-foreground")}>{dot}</span>
        <span className="font-mono text-[11px]">{session.id}</span>
        <span className="truncate text-muted-foreground">{session.title}</span>
        {session.meta.author && <span className="text-[10px] text-muted-foreground">{session.meta.author}</span>}
        {session.status && <Badge variant="outline">{session.status}</Badge>}
        {extra && <Badge variant={session.pollError ? "destructive" : "secondary"}
          title={session.pollError ?? undefined}>{extra}</Badge>}
        {(session.error || session.launchError) && (
          <span title={session.error ?? session.launchError ?? ""} className="text-destructive">⚠ error</span>)}
        <QueueItemActions>
          {session.process !== "stopped" && (
            <QueueItemAction aria-label={`Parar ${session.id}`}
              onClick={(e) => { e.stopPropagation(); stopSession(getWs(), session.id); }}>
              <Square size={11} />
            </QueueItemAction>)}
          <QueueItemAction aria-label={`Borrar ${session.id}`}
            onClick={(e) => { e.stopPropagation(); setConfirm(true); }}>
            <Trash2 size={11} />
          </QueueItemAction>
        </QueueItemActions>
      </div>
      {session.repos.map((r) => <RepoLine key={r.name} session={session} repo={r} />)}
      <ConfirmRmDialog id={session.id} open={confirm} onClose={() => setConfirm(false)} />
    </QueueItem>
  );
}
