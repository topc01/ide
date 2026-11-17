// ui/src/layout/Notifications.tsx
/** La campana (arriba a la derecha): todas las notificaciones del IDE (una sesión te espera, te piden revisar una
 *  PR, Recursos…) y arriba el resumen de revisiones pendientes (veredictos por mandar, desarrollos por pedir
 *  revisor). Lo nuevo aparece un momento como aviso; cada 5 min, si hay revisiones pendientes, un recordatorio. */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Bell, X } from "lucide-react";
import { useFolders } from "../state/folders";
import { getWs } from "../transport/wsClient";
import { notifsRead, type Notif } from "../transport/folderSessions";
import { ago } from "../modules/sessions/devStates";
import { cn } from "../lib/utils";

const REMIND_MS = 5 * 60 * 1000;

function go(focus: string | null) {
  if (!focus) return;
  const st = useFolders.getState();
  if (focus.startsWith("s:")) st.setActive(focus.slice(2));
  else if (focus.startsWith("p:")) st.setActivePr(focus.slice(2));
}

type Toast = { id: string; title: string; body?: string | null; focus?: string | null };

export function Notifications() {
  const data = useFolders((s) => s.tree.notifications);
  const items = data?.items ?? [];
  const summary = data?.summary ?? null;
  const pending = (summary?.verdicts.length ?? 0) + (summary?.reviewers.length ?? 0);
  const unread = items.filter((n) => !n.read).length;
  const [open, setOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seen = useRef<Set<string> | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const toast = (t: Toast) => {
    setToasts((x) => [...x.filter((y) => y.id !== t.id), t].slice(-3));
    window.setTimeout(() => setToasts((x) => x.filter((y) => y.id !== t.id)), 7000);
  };
  // lo nuevo (que no estaba al abrir la página) sale como aviso
  useEffect(() => {
    if (!data) return;
    if (seen.current === null) { seen.current = new Set(items.map((n) => n.id)); return; }
    for (const n of items) if (!seen.current.has(n.id)) { seen.current.add(n.id); if (!n.read) toast(n); }
  }, [items.map((n) => n.id).join(",")]);
  // recordatorio de revisiones pendientes
  const pendRef = useRef(pending); pendRef.current = pending;
  const sumRef = useRef(summary); sumRef.current = summary;
  useEffect(() => {
    const t = window.setInterval(() => {
      const s = sumRef.current;
      if (!pendRef.current || !s) return;
      const parts = [s.verdicts.length && `${s.verdicts.length} veredicto${s.verdicts.length > 1 ? "s" : ""} por mandar`,
        s.reviewers.length && `${s.reviewers.length} por pedir revisor`].filter(Boolean);
      toast({ id: `remind-${Date.now()}`, title: `Tienes ${pendRef.current} revisi${pendRef.current > 1 ? "ones" : "ón"} pendiente${pendRef.current > 1 ? "s" : ""}`,
        body: parts.join(" · ") });
    }, REMIND_MS);
    return () => window.clearInterval(t);
  }, []);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("mousedown", onDown, true); window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("mousedown", onDown, true); window.removeEventListener("keydown", onKey); };
  }, [open]);

  const click = (n: Notif) => { go(n.focus); if (!n.read) notifsRead(getWs(), n.id).catch(() => undefined); setOpen(false); };
  return createPortal(<>
    <div ref={box} className="fixed right-3 top-2 z-[60]">
      <button onClick={() => setOpen(!open)} aria-label="Notificaciones"
        className={cn("relative grid h-7 w-7 place-items-center rounded-md border bg-card text-muted-foreground hover:text-foreground",
          unread || pending ? "border-primary/60" : "border-border")}>
        <Bell size={14} />
        {(unread > 0 || pending > 0) && (
          <span className={cn("absolute -right-1.5 -top-1 min-w-[16px] rounded-full px-1 text-center font-mono text-[10px] font-bold leading-4 text-white",
            unread ? "bg-primary" : "bg-red-500")}>{unread || pending}</span>)}
      </button>
      {open && (
        <div data-float className="absolute right-0 top-9 flex max-h-[75vh] w-[380px] flex-col overflow-hidden rounded-md border border-border bg-popover text-xs shadow-xl">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <span className="flex-1 font-semibold">Notificaciones</span>
            {unread > 0 && <button onClick={() => notifsRead(getWs()).catch(() => undefined)}
              className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground">marcar leídas</button>}
            {items.length > 0 && <button onClick={() => notifsRead(getWs(), undefined, true).catch(() => undefined)}
              className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground">limpiar</button>}
          </div>
          <div className="overflow-y-auto">
            {pending > 0 && summary && (
              <div className="border-b border-border bg-red-400/[0.06] px-3 py-2">
                <div className="mb-1 font-semibold text-red-300">{pending} revisi{pending > 1 ? "ones" : "ón"} pendiente{pending > 1 ? "s" : ""}</div>
                {summary.verdicts.length > 0 && <div className="mb-1">
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Veredicto por mandar</div>
                  {summary.verdicts.map((v) => (
                    <button key={v.url} onClick={() => { go(v.sid ? `s:${v.sid}` : `p:${v.url}`); setOpen(false); }}
                      className="block w-full rounded px-1 py-0.5 text-left font-mono hover:bg-accent">{v.label}</button>))}
                </div>}
                {summary.reviewers.length > 0 && <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Listos para revisión, sin revisor pedido</div>
                  {summary.reviewers.map((r) => (
                    <button key={r.sid} onClick={() => { go(`s:${r.sid}`); setOpen(false); }}
                      className="block w-full truncate rounded px-1 py-0.5 text-left hover:bg-accent">
                      <span className="font-mono text-primary">{r.label}</span> {r.name}</button>))}
                </div>}
              </div>)}
            {!items.length && <div className="px-3 py-4 text-muted-foreground">Sin notificaciones.</div>}
            {items.map((n) => (
              <div key={n.id} className={cn("group flex items-start gap-2 border-b border-border/60 px-3 py-2 hover:bg-accent/50", !n.read && "bg-primary/[0.05]")}>
                <span className={cn("mt-1 h-1.5 w-1.5 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-primary")} />
                <button onClick={() => click(n)} className="min-w-0 flex-1 text-left">
                  <div className={cn("leading-snug", !n.read && "font-semibold")}>{n.title}</div>
                  {n.body && <div className="line-clamp-2 text-[11px] text-muted-foreground">{n.body}</div>}
                  <div className="text-[10px] text-muted-foreground">hace {ago(n.at)}</div>
                </button>
                <button onClick={() => notifsRead(getWs(), n.id, true).catch(() => undefined)} aria-label="Sacar"
                  className="hidden rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground group-hover:block"><X size={11} /></button>
              </div>))}
          </div>
        </div>)}
    </div>
    <div className="pointer-events-none fixed right-2 top-10 z-[59] flex w-[340px] flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto rounded-md border border-primary/50 bg-popover p-2.5 text-xs shadow-xl">
          <div className="flex items-start gap-2">
            <button onClick={() => { go(t.focus ?? null); setToasts((x) => x.filter((y) => y.id !== t.id)); if (!t.focus) setOpen(true); }}
              className="min-w-0 flex-1 text-left">
              <div className="font-semibold leading-snug">{t.title}</div>
              {t.body && <div className="line-clamp-2 text-[11px] text-muted-foreground">{t.body}</div>}
            </button>
            <button onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))} aria-label="Cerrar" className="rounded p-0.5 text-muted-foreground hover:text-foreground"><X size={11} /></button>
          </div>
        </div>))}
    </div>
  </>, document.body);
}
