import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import { useChanges } from "../../state/changes";

const basename = (p: string) => p.split("/").pop() || p;

export function ChangesPanel() {
  const activeSessionId = useSessions((s) => s.activeSessionId);
  const openTab = useStore((s) => s.openTab);
  const { status, error, load } = useChanges();

  useEffect(() => {
    if (activeSessionId === null) return;
    load(activeSessionId);
    const t = setInterval(() => load(activeSessionId), 4000);
    return () => clearInterval(t);
  }, [activeSessionId, load]);

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Archivos modificados
        </div>
        <button aria-label="refrescar" title="refrescar" onClick={() => load(activeSessionId)}
          className="text-muted-foreground hover:text-foreground">
          <RefreshCw size={13} />
        </button>
      </div>
      {activeSessionId === null && (
        <div className="px-1 py-2 text-xs text-muted-foreground">selecciona una sesión</div>
      )}
      {activeSessionId !== null && status && !error && (
        <div className="mb-2 flex items-center gap-2 px-1 font-mono text-[10.5px] text-muted-foreground">
          <span className="text-primary">{status.branch}</span>
          <span className="text-status-running">+{status.totalAdded}</span>
          <span className="text-[var(--destructive)]">-{status.totalRemoved}</span>
        </div>
      )}
      {activeSessionId !== null && error && (
        <div className="px-1 py-2 text-xs text-[var(--destructive)]">desconectado — {error}</div>
      )}
      {activeSessionId !== null && !error && status && status.files.length === 0 && (
        <div className="px-1 py-2 text-xs text-muted-foreground">sin cambios</div>
      )}
      {activeSessionId !== null && !error && status?.files.map((f) => (
        <button title="Ver el diff de este archivo" key={f.path}
          onClick={() => openTab({
            id: `diff:${activeSessionId ?? ""}:${f.status}:${f.path}`,
            type: "file", label: basename(f.path),
          })}
          className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 hover:bg-accent">
          <span className="min-w-0 flex-1 truncate text-left font-mono text-[11.5px] text-foreground">
            {f.path}
          </span>
          <span className="font-mono text-[10.5px] text-status-running">+{f.added ?? 0}</span>
          <span className="font-mono text-[10.5px] text-[var(--destructive)]">-{f.removed ?? 0}</span>
        </button>
      ))}
    </div>
  );
}
