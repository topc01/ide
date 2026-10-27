import { useEffect, useState } from "react";
import { RefreshCw, CornerRightDown } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import { useGraphite } from "../../state/graphite";

const basename = (p: string) => p.split("/").pop() || p;

export function GraphitePanel() {
  const activeSessionId = useSessions((s) => s.activeSessionId);
  const openTab = useStore((s) => s.openTab);
  const {
    stack, error, commitsByBranch, expandedBranches, expandedCommits,
    load, toggleBranch, toggleCommit, restack,
  } = useGraphite();
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    if (activeSessionId === null) return;
    load(activeSessionId);
    // sin polling: fetch al montar y al cambiar de sesión
  }, [activeSessionId, load]);

  if (activeSessionId === null) {
    return <div className="p-3 text-xs text-muted-foreground">selecciona una sesión</div>;
  }

  return (
    <div className="p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Stack de branches
        </div>
        <button aria-label="refrescar" title="refrescar" onClick={() => load(activeSessionId)}
          className="text-muted-foreground hover:text-foreground">
          <RefreshCw size={13} />
        </button>
      </div>
      {error && <div className="px-1 py-2 text-xs text-[var(--destructive)]">desconectado — {error}</div>}
      {!error && stack.map((b) => (
        <div key={b.name} className="mb-0.5">
          <div className="flex items-center gap-2 rounded px-1.5 py-1.5 hover:bg-accent">
            <span className="h-3 w-3 shrink-0 rounded-full border-2"
              style={{ borderColor: b.current ? "var(--primary)" : b.needsRestack ? "var(--primary)" : "var(--border)",
                       background: "var(--background)" }} />
            <button title="Ver los commits de esta rama" onClick={() => toggleBranch(activeSessionId, b.name)}
              className="min-w-0 flex-1 truncate text-left font-mono text-[11.5px]"
              style={{ color: b.current ? "var(--foreground)" : "var(--muted-foreground)" }}>
              {b.name}
            </button>
            {b.current && (
              <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wide text-primary">actual</span>
            )}
            {b.needsRestack && confirming !== b.name && (
              <button aria-label={`restack ${b.name}`} title={`restack ${b.name}`} onClick={() => setConfirming(b.name)}
                className="shrink-0 text-amber-300 hover:text-primary">
                <CornerRightDown size={13} />
              </button>
            )}
            {confirming === b.name && (
              <span className="flex shrink-0 items-center gap-1.5 text-[10px]">
                <span className="text-muted-foreground">restackear?</span>
                <button title="Confirmar el restack" className="text-status-running"
                  onClick={() => { setConfirming(null); restack(activeSessionId, b.name); }}>sí</button>
                <button title="Cancelar" className="text-muted-foreground" onClick={() => setConfirming(null)}>no</button>
              </span>
            )}
          </div>
          {expandedBranches.includes(b.name) && (
            <div className="ml-[9px] pl-3.5"
              style={{ borderLeft: b.needsRestack ? "1px dashed var(--border)" : "1px solid var(--border)" }}>
              {(commitsByBranch[b.name] ?? []).map((c) => (
                <div key={c.hash} className="my-0.5">
                  <button title="Ver los archivos de este commit" onClick={() => toggleCommit(c.hash)}
                    className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-accent">
                    <span className="shrink-0 font-mono text-[10.5px] text-primary">{c.hash}</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-foreground/80">{c.message}</span>
                  </button>
                  {expandedCommits.includes(c.hash) && (
                    <div className="pb-1 pl-4">
                      {c.files.map((f) => (
                        <button title="Ver el diff de este archivo en el commit" key={f.path}
                          onClick={() => openTab({
                            id: `diff:${activeSessionId ?? ""}:@${c.hash}:${f.path}`,
                            type: "file", label: basename(f.path),
                          })}
                          className="flex w-full items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent">
                          <span className="min-w-0 flex-1 truncate text-left font-mono text-[10.5px] text-muted-foreground">{f.path}</span>
                          <span className="font-mono text-[9.5px] text-status-running">+{f.added ?? 0}</span>
                          <span className="font-mono text-[9.5px] text-[var(--destructive)]">-{f.removed ?? 0}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
