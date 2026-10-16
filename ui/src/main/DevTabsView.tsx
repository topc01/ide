// ui/src/main/DevTabsView.tsx
import { useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";
import { useFolders } from "../state/folders";
import { claudeTab, docTab, summaryTab, useDevTabs, type DevTab } from "../state/devTabs";
import type { FolderSession, GhPr } from "../transport/folderSessions";
import { openSession, refreshReview } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { allPrs, useGithubReviews } from "../modules/sessions/ReviewsSection";
import { deriveMine } from "../modules/sessions/desarrollos";
import { repoShort } from "../modules/sessions/DevCard";
import { TerminalTab } from "./TerminalTab";
import { PrView } from "./PrView";
import { DocTab } from "./DocTab";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

interface Dev { key: string; session?: FolderSession; prs: GhPr[] }

/** El desarrollo actual: una sesión (con sus PRs), un stack sin sesión o una PR suelta. */
function useCurrentDev(): Dev | null {
  const { tree, activeId, activePrUrl } = useFolders();
  const { gh } = useGithubReviews();
  const tickets = tree.sessions.filter((s) => s.kind !== "review");
  if (activePrUrl) {
    if (!gh) return null;                     // hasta tener datos no se sabe a qué desarrollo pertenece
    const owner = deriveMine(tickets, gh).find((d) => d.session && d.prs.some((p) => p.url === activePrUrl));
    if (owner) return { key: `s:${owner.session!.id}`, session: owner.session, prs: owner.prs };
    const pr = allPrs(gh).find((p) => p.url === activePrUrl);
    if (pr?.stack) return { key: `st:${pr.stack.id}`, prs: gh.stacks?.[pr.stack.id] ?? [pr] };
    return { key: `p:${activePrUrl}`, prs: pr ? [pr] : [] };
  }
  const session = tree.sessions.find((s) => s.id === activeId);
  if (!session) return null;
  const prs = gh ? (session.kind === "review"
    ? allPrs(gh).filter((p) => p.sessionId === session.id)
    : deriveMine(tickets, gh).find((d) => d.session?.id === session.id)?.prs ?? []) : [];
  return { key: `s:${session.id}`, session, prs };
}

const prLabel = (p: GhPr) => `${repoShort(p.repo)} #${p.number}`;

/** El `claude` de una sesión: se abre solo si está parada; reintentar si falla; aviso de commits nuevos. */
function ClaudeTab({ session }: { session: FolderSession }) {
  const [error, setError] = useState<string | null>(null);
  const tried = useRef<string | null>(null);
  useEffect(() => {                            // una vez por sesión: si está parada, lanzarla
    if (tried.current === session.id) return;
    tried.current = session.id;
    if (session.process === "stopped" && !session.terminalId && !session.launchError) {
      openSession(getWs(), session.id).catch((e: any) => setError(e?.message ?? String(e)));
    }
  }, [session.id, session.process, session.terminalId, session.launchError]);
  const act = (p: Promise<unknown>) => p.catch((e: any) => setError(e?.message ?? String(e)));
  return (
    <div className="flex h-full flex-col">
      {session.prState === "stale" && (
        <div className="flex items-center gap-2 bg-accent px-3 py-1 text-xs">
          El PR tiene commits nuevos desde tu revisión.
          <Button title="Mover el worktree al head nuevo del PR" size="sm" onClick={() => act(refreshReview(getWs(), session.id))}>Refrescar</Button>
        </div>)}
      {error && <p role="alert" className="px-3 py-1 text-xs text-destructive">{error}</p>}
      <div className="relative min-h-0 flex-1">
        {session.terminalId ? <TerminalTab key={session.terminalId} id={session.terminalId} /> : (
          <div className="flex flex-col items-start gap-2 p-6 text-sm">
            {session.process === "queued" ? <span className="text-muted-foreground">En cola (max_running)…</span> : (<>
              {session.launchError && <p role="alert" className="text-xs text-destructive">{session.launchError}</p>}
              {session.launchError || error
                ? <Button title="Volver a lanzar claude en esta sesión" onClick={() => { setError(null); act(openSession(getWs(), session.id)); }}>Reintentar</Button>
                : <span className="text-muted-foreground">abriendo…</span>}
            </>)}
          </div>)}
      </div>
    </div>
  );
}

/** Panel principal: cada desarrollo tiene su fila de tabs (claude, doc, resumen de PR, scripts). */
export function DevTabsView() {
  const dev = useCurrentDev();
  const { activePrUrl, setActivePr, setActive } = useFolders();
  const { byDev, open, close, focus } = useDevTabs();
  // la tab activa y "lo elegido" van juntos: una tab de resumen elige esa PR; claude/doc/script, la sesión
  const select = (t: DevTab, how: "focus" | "open") => {
    if (!dev) return;
    if (how === "open") open(dev.key, t); else focus(dev.key, t.id);
    if (t.url && t.url !== activePrUrl) setActivePr(t.url);
    else if (!t.url && dev.session && activePrUrl) setActive(dev.session.id);
  };
  const [menu, setMenu] = useState(false);

  // al elegir: la PR elegida abre/enfoca su resumen; una sesión sin tabs arranca con `claude`
  useEffect(() => {
    if (!dev) return;
    if (activePrUrl) {
      const pr = dev.prs.find((p) => p.url === activePrUrl);
      open(dev.key, summaryTab(activePrUrl, pr ? prLabel(pr) : "PR"));
    } else if (dev.session && !useDevTabs.getState().byDev[dev.key]?.tabs.length) {
      open(dev.key, claudeTab(dev.session.id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dev?.key, activePrUrl]);

  if (!dev) return <div className="p-6 text-sm text-muted-foreground">Elige un desarrollo en la sidebar (o crea la principal con ★).</div>;
  const state = byDev[dev.key] ?? { tabs: [], active: null };
  const active = state.tabs.find((t) => t.id === state.active) ?? null;
  const s = dev.session;
  const docName = s?.kind === "review" ? "REVIEW.md" : s?.kind === "ticket" ? "TICKET.md" : null;
  const candidates: DevTab[] = [
    ...(s ? [claudeTab(s.id)] : []),
    ...(s && docName ? [docTab(s.id, docName)] : []),
    ...dev.prs.map((p) => summaryTab(p.url, prLabel(p))),
  ].filter((t) => !state.tabs.some((x) => x.id === t.id));

  return (
    <div className="flex h-full flex-col">
      <div role="tablist" className="flex items-stretch border-b border-border bg-title-bg">
        {state.tabs.map((t) => (
          <span key={t.id} className={cn("group/tab flex items-center gap-1 border-b-2 pl-3 pr-1 text-xs",
            t.id === state.active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
            <button role="tab" aria-selected={t.id === state.active} title={t.label} className="py-1.5"
              onClick={() => select(t, "focus")}>{t.label}</button>
            <button aria-label={`Cerrar ${t.label}`} title={`Cerrar ${t.label} (no para nada: claude sigue)`}
              onClick={() => close(dev.key, t.id)}
              className="rounded p-0.5 opacity-0 hover:bg-accent group-hover/tab:opacity-100"><X size={11} /></button>
          </span>))}
        <div className="relative flex items-center px-1">
          <button aria-label="Abrir tab" title="Abrir otra tab de este desarrollo" disabled={!candidates.length}
            onClick={() => setMenu((m) => !m)}
            className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30">
            <Plus size={13} /></button>
          {menu && candidates.length > 0 && (
            <div role="menu" className="absolute left-0 top-full z-30 mt-1 w-48 rounded-md border border-border bg-popover p-1 shadow">
              {candidates.map((t) => (
                <button key={t.id} role="menuitem" title={`Abrir ${t.label}`}
                  onClick={() => { select(t, "open"); setMenu(false); }}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">{t.label}</button>))}
            </div>)}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {!active && <div className="p-6 text-sm text-muted-foreground">No hay tabs abiertas: ábrelas con el +.</div>}
        {active?.kind === "claude" && s && <ClaudeTab session={s} />}
        {active?.kind === "doc" && active.sid && <DocTab id={active.sid} />}
        {active?.kind === "summary" && active.url && <div className="h-full overflow-auto"><PrView url={active.url} /></div>}
        {active?.kind === "script" && active.terminalId && <TerminalTab key={active.terminalId} id={active.terminalId} />}
      </div>
    </div>
  );
}
