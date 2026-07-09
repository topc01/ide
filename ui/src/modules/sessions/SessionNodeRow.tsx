import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import type { SessionNode } from "../../transport/sessions";
import { renameSession } from "../../transport/sessions";
import { getWs } from "../../transport/wsClient";
import { useSessions } from "../../state/sessions";

const DOT: Record<string, string> = {
  running: "var(--status-running)", idle: "var(--status-idle)", done: "var(--status-done)",
};

export function SessionNodeRow({ node, depth }: { node: SessionNode; depth: number }) {
  const { activeSessionId, setActive, toggleExpanded, openModal, editingId, startRename, stopRename } = useSessions();
  const active = activeSessionId === node.id;
  const hasChildren = node.children.length > 0;
  const [draft, setDraft] = useState(node.name);
  return (
    <div>
      <div
        data-session-row
        onClick={() => setActive(node.id)}
        style={{
          display: "flex", alignItems: "center", gap: 6, height: 26, cursor: "pointer",
          paddingLeft: depth * 16, paddingRight: 6, fontSize: 12,
          color: active ? "var(--text-primary)" : "var(--text-secondary)",
          background: active ? "var(--selected-bg)" : "transparent",
          borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
        }}
      >
        <ChevronRight
          size={12}
          onClick={(e) => { e.stopPropagation(); if (hasChildren) toggleExpanded(node.id); }}
          style={{
            color: "var(--text-muted)", flexShrink: 0,
            visibility: hasChildren ? "visible" : "hidden",
            transform: node.expanded ? "rotate(90deg)" : "none", transition: "transform .12s",
          }}
        />
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: DOT[node.status], flexShrink: 0 }} />
        {editingId === node.id ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                renameSession(getWs(), node.id, draft).catch((err) => console.error("rename falló", err));
                stopRename();
              }
              if (e.key === "Escape") stopRename();
            }}
            onBlur={stopRename}
            style={{ flex: 1, fontSize: 12, background: "var(--terminal-bg)",
              color: "var(--text-primary)", border: "1px solid var(--accent)", borderRadius: 4, padding: "1px 4px" }}
          />
        ) : (
          <span
            onDoubleClick={(e) => { e.stopPropagation(); setDraft(node.name); startRename(node.id); }}
            style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {node.name}
          </span>
        )}
        {node.role && (
          <span style={{
            fontSize: 10, padding: "1px 6px", borderRadius: 4,
            background: "#2e2820", color: "var(--accent)",
          }}>{node.role}</span>
        )}
        <Plus
          size={13}
          onClick={(e) => { e.stopPropagation(); openModal(node.id); }}
          style={{ color: "var(--text-muted)", flexShrink: 0 }}
        />
      </div>
      {node.expanded && node.children.map((c) => (
        <SessionNodeRow key={c.id} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}
