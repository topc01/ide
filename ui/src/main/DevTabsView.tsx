// ui/src/main/DevTabsView.tsx
import { useClaudeFocus } from "../layout/devShortcuts";
import { useEffect, useRef, useState } from "react";
import { Bot, Paperclip, Plus, X } from "lucide-react";
import { useFolders } from "../state/folders";
import { attachmentTab, claudeTab, consultTab, docTab, fileTab, scriptTab, summaryTab, useDevTabs, type DevTab } from "../state/devTabs";
import { resolvePath } from "./pathLinks";
import type { FolderSession, GhPr } from "../transport/folderSessions";
import { attachFile, isHtml, openHtmlAttachment, closeConsult, consultLast, consultSend, newSessionForPr, openConsult, openSession, refreshReview, resumeSession, startReview } from "../transport/folderSessions";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../components/ui/dialog";
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
import { ACTIVITY, activityOf, waitTime } from "../modules/sessions/activity";
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
    if (session.process === "stopped" && !session.terminalId && !session.launchError && !session.paused) {
      openSession(getWs(), session.id).catch((e: any) => setError(e?.message ?? String(e)));
    }
  }, [session.id, session.process, session.terminalId, session.launchError]);
  const act = (p: Promise<unknown>) => p.catch((e: any) => setError(e?.message ?? String(e)));
  // rutas que menciona claude: un adjunto o un archivo de sus worktrees se abre en una tab con un click
  const dev = useCurrentDev();
  const openTab = useDevTabs((s) => s.open);
  const onPath = (raw: string) => {
    const t = dev ? resolvePath(raw, session) : null;
    if (t?.kind === "attachment" && isHtml(t.name)) return () => { openHtmlAttachment(session.id, t.name); };
    return t && dev ? () => openTab(dev.key, t.kind === "attachment" ? attachmentTab(session.id, t.name) : fileTab(session.id, t.repo, t.path)) : null;
  };
  // adjuntos: el archivo va a la carpeta de la sesión y su ruta se pega en el input de claude
  const fileRef = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState<Terminal | null>(null);   // para enfocar la terminal
  // Enter en la página (devShortcuts): el cursor al input de claude, para escribir altiro
  const focusReq = useClaudeFocus();
  useEffect(() => {
    if (focusReq.sid !== session.id || !term) return;
    if (Date.now() - focusReq.at > 5000) { useClaudeFocus.setState({ sid: null }); return; }   // pedido viejo
    term.focus();
    useClaudeFocus.setState({ sid: null });
  }, [focusReq.at, focusReq.sid, term, session.id]);
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
          <TerminalTab key={session.terminalId} id={session.terminalId} onTerm={setTerm} onPath={onPath} />) : (
          <div className="flex flex-col items-start gap-2 p-6 text-sm">
            {session.paused && session.process !== "running" ? (<>
              <span className="text-muted-foreground">Pausada desde las {session.paused.at.slice(11, 16)}: su claude está cerrado.</span>
              <Button title="Relanzar su claude con la misma conversación y decirle que siga"
                onClick={() => { setError(null); act(resumeSession(getWs(), session.id)); }}>Reanudar</Button>
            </>) : session.process === "queued" ? <span className="text-muted-foreground">En cola (max_running)…</span> : (<>
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

/** El claude de consulta: una bifurcación de la conversación de la sesión en modo plan (no edita ni hace cambios).
 *  «Mandar a la sesión» trae su último mensaje, lo puedes editar y se lo manda a la sesión. */
function ConsultTab({ session, terminalId }: { session: FolderSession; terminalId: string }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const alive = session.consult?.terminalId === terminalId;
  const prepare = () => { setMsg(null); consultLast(getWs(), session.id).then((r) => setDraft(r.text || ""))
    .catch((e: any) => setMsg(e?.message ?? String(e))); };
  const send = () => {
    if (!draft?.trim()) return;
    setBusy(true);
    consultSend(getWs(), session.id, draft).then((r) => { setDraft(null); setMsg(`Mandado a la sesión (${r.how}).`); })
      .catch((e: any) => setMsg(e?.message ?? String(e))).finally(() => setBusy(false));
  };
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border bg-violet-500/10 px-3 py-1 text-[11px]">
        <span className="text-violet-300">Consulta · solo lectura (modo plan): arrancó con toda la conversación de la sesión y no edita ni hace cambios.</span>
        {msg && <span className="text-muted-foreground">{msg}</span>}
        <span className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" disabled={!alive} title="Trae el último mensaje de la consulta para revisarlo y mandárselo a la sesión" onClick={prepare}>Mandar a la sesión…</Button>
        </span>
      </div>
      <div className="min-h-0 flex-1">
        {alive ? <TerminalTab key={terminalId} id={terminalId} />
          : <p className="p-6 text-sm text-muted-foreground">La consulta se cerró. Abre otra con el + (claude de consulta).</p>}
      </div>
      {draft !== null && (
        <Dialog open onOpenChange={(o) => { if (!o) setDraft(null); }}>
          <DialogContent className="max-w-2xl">
            <DialogHeader><DialogTitle className="text-sm">Mandar a la sesión</DialogTitle></DialogHeader>
            <p className="text-[11px] text-muted-foreground">El último mensaje de la consulta. Edítalo si quieres: le llega a la sesión como mensaje tuyo (si está pausada, al reanudarla).</p>
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} aria-label="Texto para la sesión"
              placeholder="(la consulta todavía no escribió nada)"
              className="min-h-56 w-full resize-y rounded-md border border-border bg-muted p-2 font-mono text-xs text-foreground outline-none focus:border-primary" />
            <DialogFooter className="gap-2">
              <Button size="sm" variant="ghost" title="No mandar" onClick={() => setDraft(null)}>Cancelar</Button>
              <Button size="sm" disabled={busy || !draft.trim()} title="Mandárselo a la sesión" onClick={send}>{busy ? "Mandando…" : "Mandar"}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>)}
    </div>);
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

  // Enter (devShortcuts): pasar a la tab `claude` de la sesión (ClaudeTab enfoca su input)
  const focusSid = useClaudeFocus((st) => st.sid);
  useEffect(() => {
    if (dev?.session && focusSid === dev.session.id) open(dev.key, claudeTab(dev.session.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusSid, dev?.key]);

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
  const newConsult = () => run("consulta", openConsult(getWs(), s!.id).then((r) => { open(dev.key, consultTab(s!.id, r.terminalId)); }));
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
        {/* la tab claude va primera y destacada (con la actividad de la sesión) */}
        {[...state.tabs].sort((a, b) => Number(b.kind === "claude") - Number(a.kind === "claude")).map((t) => {
          const isClaude = t.kind === "claude";
          const act = isClaude && s ? ACTIVITY[activityOf(s)] : null;
          return (
          <span key={t.id} className={cn("group/tab flex items-center gap-1 border-b-2 pl-3 pr-1 text-xs",
            isClaude && "mr-1 rounded-t-md bg-primary/10 pl-2.5 font-semibold",
            t.id === state.active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            isClaude && t.id !== state.active && "text-primary/80")}>
            <button role="tab" aria-selected={t.id === state.active}
              title={isClaude && act ? `claude — ${act[2]}${waitTime(s) ? ` (terminó a las ${waitTime(s)})` : ""}${s?.activity?.note && s.activity.state === "waiting" ? `: ${s.activity.note}` : ""}` : t.label}
              className="flex items-center gap-1.5 py-1.5" onClick={() => select(t, "focus")}>
              {isClaude && <Bot size={13} className="text-primary" />}
              {t.kind === "run" && <span className="mr-1"><RunState compact
                run={runs.state?.runs.find((r) => r.place === t.place && r.repo === t.repo && r.name === t.name)} /></span>}
              {t.label}
              {act && <span aria-hidden className={cn("text-[10px]", act[1])}>{act[0]}</span>}</button>
            <button aria-label={`Cerrar ${t.label}`} title={t.kind === "consult" ? "Cerrar la consulta (cierra ese claude; la sesión sigue igual)" : `Cerrar ${t.label} (no para nada: claude sigue)`}
              onClick={() => { if (t.kind === "consult" && t.sid) closeConsult(getWs(), t.sid).catch(() => {}); close(dev.key, t.id); }}
              className="rounded p-0.5 opacity-0 hover:bg-accent group-hover/tab:opacity-100"><X size={11} /></button>
          </span>);
        })}
        <div className="relative flex items-center px-1">
          <button aria-label="Nueva tab" title="Nueva tab: terminal, sesión de revisión o reabrir una cerrada"
            onClick={() => setMenu((m) => !m)}
            className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30">
            <Plus size={13} /></button>
          {busy && <span className="ml-1 text-[11px] text-muted-foreground">{busy === "terminal" ? "abriendo terminal…" : busy === "consulta" ? "abriendo consulta…" : "creando sesión…"}</span>}
          {actionError && <span role="alert" title={actionError} className="ml-1 text-[11px] text-destructive">⚠ {actionError}</span>}
          {menu && (
            <div role="menu" className="absolute left-0 top-full z-30 mt-1 w-56 rounded-md border border-border bg-popover p-1 shadow">
              <div className="px-2 pb-0.5 pt-1 text-[10px] uppercase tracking-wide text-muted-foreground">Crear</div>
              {s ? (
                <button role="menuitem" title="Shell en la carpeta de la sesión (donde están sus worktrees)" onClick={newTerminal}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">Terminal nueva</button>
              ) : null}
              {s && (
                <button role="menuitem" title="Otro claude que arranca con toda la conversación de esta sesión y sigue por su lado, en solo lectura (modo plan): para preguntar sin cortarle el trabajo. Cerrar su tab lo cierra"
                  onClick={newConsult}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">Claude de consulta (solo lectura)</button>)}
              {s ? null : canDevelop ? (
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
        {active?.kind === "consult" && s && active.terminalId && <ConsultTab session={s} terminalId={active.terminalId} />}
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
