// ui/src/main/DevTabsView.tsx
import { useEffect, useRef, useState } from "react";
import { Paperclip, Plus, X } from "lucide-react";
import { useFolders } from "../state/folders";
import { claudeTab, docTab, scriptTab, summaryTab, useDevTabs, type DevTab } from "../state/devTabs";
import type { FolderSession, GhPr } from "../transport/folderSessions";
import { attachFile, newSessionForPr, openSession, refreshReview, startReview } from "../transport/folderSessions";
import { openTerminal } from "../transport/terminalChannel";
import { getWs } from "../transport/wsClient";
import { useGithubReviews } from "../modules/sessions/ReviewsSection";
import { useCurrentDev } from "./currentDev";
import { repoShort } from "../modules/sessions/DevCard";
import { TerminalTab } from "./TerminalTab";
import { PrView } from "./PrView";
import { DocTab } from "./DocTab";
import { RunLogTab } from "./RunLogTab";
import { FileTab } from "./FileTab";
import { PrDiffTab } from "./PrDiffTab";
import { AttachmentTab } from "./AttachmentTab";
import { PinOverlay } from "./PinOverlay";
import type { Terminal } from "@xterm/xterm";
import { useRuns } from "../transport/runs";
import { RunState } from "../modules/servers/ServersPanel";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

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
  // adjuntos: el archivo va a la carpeta de la sesión y su ruta se pega en el input de claude
  const fileRef = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState<Terminal | null>(null);   // para pinear mensajes con hover
  const [drag, setDrag] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const upload = (files: FileList) => {
    for (const f of Array.from(files)) {
      if (f.size > 10 * 1024 * 1024) { setNote(`${f.name}: pesa más de 10 MB`); continue; }
      const r = new FileReader();
      r.onload = () => {
        const data = String(r.result).split(",", 2)[1] ?? "";
        setNote(`adjuntando ${f.name}…`);
        attachFile(getWs(), session.id, f.name || "pegado.png", data)
          .then((res) => setNote(res.pasted ? `${f.name} adjuntado (Enter para mandarlo)` : `${f.name} guardado en attachments/ (claude no está corriendo)`))
          .catch((e: any) => setNote(`⚠ ${e?.message ?? String(e)}`));
      };
      r.readAsDataURL(f);
    }
  };
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(null), 6000); return () => clearTimeout(t); }, [note]);
  return (
    <div className="flex h-full flex-col">
      {session.prState === "stale" && (
        <div className="flex items-center gap-2 bg-accent px-3 py-1 text-xs">
          El PR tiene commits nuevos desde tu revisión.
          <Button title="Mover el worktree al head nuevo del PR" size="sm" onClick={() => act(refreshReview(getWs(), session.id))}>Refrescar</Button>
        </div>)}
      {error && <p role="alert" className="px-3 py-1 text-xs text-destructive">{error}</p>}
      <div className="relative min-h-0 flex-1" onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDrag(true); } }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { if (e.dataTransfer.files.length) { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); } }}
        onPasteCapture={(e) => { if (e.clipboardData.files.length) { e.preventDefault(); e.stopPropagation(); upload(e.clipboardData.files); } }}>
        {session.terminalId && (
          <div className="absolute right-3 top-2 z-10 flex items-center gap-2">
            {note && <span className="rounded bg-card/90 px-2 py-0.5 text-[11px] text-muted-foreground shadow">{note}</span>}
            <button title="Adjuntar archivos a la conversación (también: arrastrarlos o pegarlos con ⌘V)" aria-label="Adjuntar archivos"
              onClick={() => fileRef.current?.click()}
              className="rounded-md border border-border bg-card/90 p-1.5 text-muted-foreground shadow hover:text-foreground"><Paperclip size={13} /></button>
            <input ref={fileRef} type="file" multiple hidden onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = ""; }} />
          </div>)}
        {drag && <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center border-2 border-dashed border-primary bg-background/70 text-sm text-primary">
          Suelta para adjuntar a la conversación</div>}
        {session.terminalId ? (
          <PinOverlay term={term} sid={session.id} devKey={`s:${session.id}`}>
            <TerminalTab key={session.terminalId} id={session.terminalId} onTerm={setTerm} />
          </PinOverlay>) : (
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
  const { gh } = useGithubReviews();
  const { byDev, open, close, focus } = useDevTabs();
  const runs = useRuns();                       // estado de los scripts para las tabs de log
  // la tab activa y "lo elegido" van juntos: una tab de resumen elige esa PR; claude/doc/script, la sesión
  const select = (t: DevTab, how: "focus" | "open") => {
    if (!dev) return;
    if (how === "open") open(dev.key, t); else focus(dev.key, t.id);
    if (t.url && t.url !== activePrUrl) setActivePr(t.url);
    else if (!t.url && dev.session && activePrUrl) setActive(dev.session.id);
  };
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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
  const docName = s?.kind === "review" || s?.kind === "ticket" ? "SESSION.md" : null;
  // acciones que crean algo nuevo (además de reabrir tabs cerradas)
  const run = (what: string, p: Promise<void>) => {
    setBusy(what); setActionError(null); setMenu(false);
    p.catch((e: any) => setActionError(e?.message ?? String(e))).finally(() => setBusy(null));
  };
  const newTerminal = () => run("terminal", openTerminal(getWs(), { sessionId: s!.id }).then((r: any) => {
    const n = (state.tabs.filter((t) => t.label.startsWith("terminal")).length) + 1;
    open(dev.key, scriptTab(r.id, n > 1 ? `terminal ${n}` : "terminal"));
  }));
  const reviewPr = dev.prs.find((p) => p.url === activePrUrl) ?? dev.prs[0];
  const canReview = !s && !!reviewPr && !!gh?.me && reviewPr.author !== `@${gh.me}`;
  // PR propia sin sesión: sesión en la rama de la de más arriba del stack (contiene a todas)
  const topPr = dev.prs[dev.prs.length - 1];
  const canDevelop = !s && !!topPr && !!gh?.me && topPr.author === `@${gh.me}`;
  const newDevSession = () => run("review", newSessionForPr(getWs(), topPr!.url).then((r) => { setActive(r.session.id); }));
  const newReview = () => run("review", startReview(getWs(), reviewPr!.url).then((r) => { setActive(r.id); }));
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
              onClick={() => select(t, "focus")}>
              {t.kind === "run" && <span className="mr-1"><RunState compact
                run={runs.state?.runs.find((r) => r.place === t.place && r.repo === t.repo && r.name === t.name)} /></span>}
              {t.label}</button>
            <button aria-label={`Cerrar ${t.label}`} title={`Cerrar ${t.label} (no para nada: claude sigue)`}
              onClick={() => close(dev.key, t.id)}
              className="rounded p-0.5 opacity-0 hover:bg-accent group-hover/tab:opacity-100"><X size={11} /></button>
          </span>))}
        <div className="relative flex items-center px-1">
          <button aria-label="Nueva tab" title="Nueva tab: terminal, sesión de revisión o reabrir una cerrada"
            onClick={() => setMenu((m) => !m)}
            className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30">
            <Plus size={13} /></button>
          {busy && <span className="ml-1 text-[11px] text-muted-foreground">{busy === "terminal" ? "abriendo terminal…" : "creando sesión…"}</span>}
          {actionError && <span role="alert" title={actionError} className="ml-1 text-[11px] text-destructive">⚠ {actionError}</span>}
          {menu && (
            <div role="menu" className="absolute left-0 top-full z-30 mt-1 w-56 rounded-md border border-border bg-popover p-1 shadow">
              <div className="px-2 pb-0.5 pt-1 text-[10px] uppercase tracking-wide text-muted-foreground">Crear</div>
              {s ? (
                <button role="menuitem" title="Shell en la carpeta de la sesión (donde están sus worktrees)" onClick={newTerminal}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">Terminal nueva</button>
              ) : canDevelop ? (
                <button role="menuitem" title={`Sesión de claude con el worktree en la rama ${topPr!.head} (queda en este mismo desarrollo)`}
                  onClick={newDevSession}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">Sesión en {topPr!.head}</button>
              ) : canReview ? (
                <button role="menuitem" title={`Crear la sesión de revisión de ${prLabel(reviewPr!)} y abrir su claude`} onClick={newReview}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">Sesión de revisión ({prLabel(reviewPr!)})</button>
              ) : (
                <p className="px-2 py-1 text-[11px] text-muted-foreground">Sin sesión: para una terminal, crea primero una sesión.</p>
              )}
              {candidates.length > 0 && <div className="px-2 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">Reabrir</div>}
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
        {active?.kind === "run" && active.place && active.repo && active.name &&
          <RunLogTab key={active.id} place={active.place} repo={active.repo} name={active.name} />}
        {active?.kind === "attachment" && active.sid && active.name && <AttachmentTab key={active.id} sid={active.sid} name={active.name} />}
        {active?.kind === "db" && active.url &&
          <iframe key={active.id} src={active.url} title={active.label} className="h-full w-full border-0 bg-white" />}
        {active?.kind === "diff" && active.url && active.path &&
          <PrDiffTab key={active.id} url={active.url} path={active.path} oldPath={active.oldPath ?? null} />}
        {active?.kind === "file" && active.place && active.repo && active.path &&
          <FileTab key={active.id} place={active.place} repo={active.repo} path={active.path} />}
      </div>
    </div>
  );
}
