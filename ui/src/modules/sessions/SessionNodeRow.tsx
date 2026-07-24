import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import type { SessionNode } from "../../transport/sessions";
import { renameSession } from "../../transport/sessions";
import { getWs } from "../../transport/wsClient";
import { useSessions } from "../../state/sessions";
import { cn } from "../../lib/utils";
import { Badge } from "../../components/ui/badge";
import { Input } from "../../components/ui/input";

const DOT: Record<string, string> = {
  running: "bg-status-running", idle: "bg-status-idle", done: "bg-status-done",
};

// pwd resumido: últimos 2 segmentos con "…/" (el completo va en el title/hover).
function shortPath(p: string): string {
  const segs = p.split("/").filter(Boolean);
  return segs.length > 2 ? `…/${segs.slice(-2).join("/")}` : p;
}

export function SessionNodeRow({ node, depth }: { node: SessionNode; depth: number }) {
  const { activeSessionId, setActive, toggleExpanded, openModal, editingId, startRename, stopRename, applyRename } = useSessions();
  const active = activeSessionId === node.id;
  const hasChildren = node.children.length > 0;
  const [draft, setDraft] = useState(node.name);
  return (
    <div>
      <div
        data-session-row
        onClick={() => setActive(node.id)}
        style={{ paddingLeft: depth * 16 }}
        className={cn(
          "flex h-[26px] items-center gap-1.5 pr-1.5 text-xs cursor-pointer border-l-2",
          active ? "bg-accent text-foreground border-primary" : "text-muted-foreground border-transparent hover:text-foreground",
        )}
      >
        <ChevronRight
          size={12}
          onClick={(e) => { e.stopPropagation(); if (hasChildren) toggleExpanded(node.id); }}
          className={cn(
            "shrink-0 text-muted-foreground transition-transform",
            hasChildren ? "visible" : "invisible",
            node.expanded && "rotate-90",
          )}
        />
        <span className={cn("h-[7px] w-[7px] shrink-0 rounded-full", DOT[node.status])} />
        {editingId === node.id ? (
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                applyRename(node.id, draft);
                renameSession(getWs(), node.id, draft).catch((err) => console.error("rename falló", err));
                stopRename();
              }
              if (e.key === "Escape") stopRename();
            }}
            onBlur={stopRename}
            className="h-5 flex-1 px-1 py-0 text-xs"
          />
        ) : (
          <span
            onDoubleClick={(e) => { e.stopPropagation(); setDraft(node.name); startRename(node.id); }}
            className="flex-1 truncate"
          >
            {node.name}
          </span>
        )}
        {node.role && (
          <Badge variant="secondary" className="bg-role-pill text-primary text-[10px] px-1.5 py-0">
            {node.role}
          </Badge>
        )}
        <Plus
          size={13}
          onClick={(e) => { e.stopPropagation(); openModal(node.id); }}
          className="shrink-0 text-muted-foreground"
        />
      </div>
      {(node.worktreePath || node.branch) && (
        <div
          data-session-meta
          style={{ paddingLeft: depth * 16 + 22 }}
          className="flex items-center gap-2 pb-0.5 pr-1.5 text-[10px] text-muted-foreground"
        >
          {node.worktreePath && (
            <span title={node.worktreePath} className="truncate font-mono">{shortPath(node.worktreePath)}</span>
          )}
          {node.branch && (
            <span className="shrink-0 font-mono text-primary">⎇ {node.branch}</span>
          )}
        </div>
      )}
      {node.expanded && node.children.map((c) => (
        <SessionNodeRow key={c.id} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}
