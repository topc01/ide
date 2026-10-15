import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useFolders } from "../state/folders";
import { fetchDoc, onSessionsChanged, openSession, refreshReview } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { TerminalTab } from "./TerminalTab";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

type TabKey = "claude" | "doc" | string;      // string = terminalId de un script

function DocTab({ id }: { id: string }) {
  const [text, setText] = useState(""); const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const load = () => fetchDoc(getWs(), id).then((d) => { setText(d.text); setError(null); }).catch((e) => setError(e?.message ?? String(e)));
    load();
    return onSessionsChanged(getWs(), load);
  }, [id]);
  if (error) return <p role="alert" className="p-4 text-xs text-destructive">{error}</p>;
  return <pre className="h-full overflow-auto whitespace-pre-wrap p-4 font-mono text-xs">{text}</pre>;
}

export function SessionView() {
  const { tree, activeId, scriptTabs, closeScriptTab } = useFolders();
  const [tab, setTab] = useState<TabKey>("claude");
  const [mounted, setMounted] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const session = tree.sessions.find((s) => s.id === activeId);
  const scripts = activeId ? scriptTabs[activeId] ?? [] : [];

  useEffect(() => { setTab("claude"); setError(null); }, [activeId]);
  // Seleccionar una sesión parada la abre (una vez por selección; si falla queda el botón para reintentar)
  const shouldOpen = !!session && session.process === "stopped" && !session.terminalId && !session.launchError;
  useEffect(() => {
    if (!activeId || !shouldOpen) return;
    openSession(getWs(), activeId).catch((e: any) => setError(e?.message ?? String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);
  const visibleTerm = tab === "claude" ? session?.terminalId ?? null
    : tab === "doc" ? null : tab;
  useEffect(() => {
    if (visibleTerm && !mounted.includes(visibleTerm)) setMounted((m) => [...m, visibleTerm]);
  }, [visibleTerm, mounted]);

  if (!session) {
    return <div className="p-6 text-sm text-muted-foreground">Elige una sesión del sidebar (o crea la principal con ★).</div>;
  }
  const docName = session.kind === "review" ? "REVIEW.md" : session.kind === "ticket" ? "TICKET.md" : null;
  const tabCls = (active: boolean) => cn("flex items-center gap-1.5 border-b-2 px-3 py-1.5 text-xs",
    active ? "border-primary text-foreground" : "border-transparent text-muted-foreground");
  const act = (p: Promise<unknown>) => p.catch((e: any) => setError(e?.message ?? String(e)));

  return (
    <div className="flex h-full flex-col">
      <div role="tablist" className="flex border-b border-border bg-title-bg">
        <button role="tab" aria-selected={tab === "claude"} className={tabCls(tab === "claude")} onClick={() => setTab("claude")}>claude</button>
        {docName && <button role="tab" aria-selected={tab === "doc"} className={tabCls(tab === "doc")} onClick={() => setTab("doc")}>{docName}</button>}
        {scripts.map((s) => (
          <span key={s.terminalId} className={tabCls(tab === s.terminalId)}>
            <button role="tab" aria-selected={tab === s.terminalId} onClick={() => setTab(s.terminalId)}>{s.label}</button>
            <button aria-label={`cerrar ${s.label}`} onClick={() => { closeScriptTab(session.id, s.terminalId); setTab("claude"); }}><X size={11} /></button>
          </span>
        ))}
      </div>
      {session.prState === "stale" && (
        <div className="flex items-center gap-2 bg-accent px-3 py-1 text-xs">
          El PR tiene commits nuevos desde tu revisión.
          <Button size="sm" onClick={() => act(refreshReview(getWs(), session.id))}>Refrescar</Button>
        </div>
      )}
      {error && <p role="alert" className="px-3 py-1 text-xs text-destructive">{error}</p>}
      <div className="relative min-h-0 flex-1">
        {mounted.map((tid) => (
          <div key={tid} hidden={tid !== visibleTerm} className="h-full"><TerminalTab id={tid} /></div>
        ))}
        {tab === "claude" && !session.terminalId && (
          <div className="flex flex-col items-start gap-2 p-6 text-sm">
            {session.process === "queued" ? <span className="text-muted-foreground">En cola (max_running)…</span> : (
              <>
                {session.launchError && <p role="alert" className="text-xs text-destructive">{session.launchError}</p>}
                {session.launchError || error
                  ? <Button onClick={() => { setError(null); act(openSession(getWs(), session.id)); }}>Reintentar</Button>
                  : <span className="text-muted-foreground">abriendo…</span>}
              </>
            )}
          </div>
        )}
        {tab === "doc" && <DocTab id={session.id} />}
      </div>
    </div>
  );
}
