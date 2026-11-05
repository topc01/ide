// ui/src/layout/StatusBar.tsx
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useFolders } from "../state/folders";
import { isWaiting, waitTime } from "../modules/sessions/activity";
import { fetchUsage, type Usage, type UsageWindow } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { cn } from "../lib/utils";

const POLL_MS = 5000;   // solo lee estado del server (sin tokens); el server consulta límites cada 60 s

function untilReset(iso: string | null, now: number): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - now;
  if (!(ms > 0)) return "ya";
  const m = Math.floor(ms / 60000), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60);
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m % 60}m` : `${m}m`;
}

const tone = (pct: number) => pct >= 90 ? "text-destructive" : pct >= 70 ? "text-primary" : "text-foreground";
const fmtK = (n: number) => n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : `${Math.round(n / 1000)}k`;

function Meter({ pct }: { pct: number }) {
  return (
    <span className="inline-block h-1.5 w-16 overflow-hidden rounded-sm bg-muted align-middle">
      <span className={cn("block h-full", pct >= 90 ? "bg-destructive" : "bg-primary")}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </span>
  );
}

function Window({ label, w, now }: { label: string; w: UsageWindow | null; now: number }) {
  if (!w) return <span className="text-muted-foreground">{label} —</span>;
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-muted-foreground">{label}</span><Meter pct={w.percent} />
      <span className={tone(w.percent)}>{Math.round(w.percent)}%</span>
      <span className="text-muted-foreground">· reinicia en {untilReset(w.resetsAt, now)}</span>
    </span>
  );
}

/** Barra inferior: contexto de la sesión abierta + ventanas de 5 h y semanal de Claude Code. */
export function StatusBar() {
  const activeId = useFolders((s) => s.activeId);
  const mainId = useFolders((s) => s.tree.sessions.find((x) => x.kind === "main")?.id);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const [update, setUpdate] = useState<{ pending: boolean; idleBefore: number } | null>(null);
  useEffect(() => {
    const ws = getWs();
    ws.request("server.status", {}).then(setUpdate).catch(() => { /* server viejo */ });
    const cb = (p: any) => setUpdate(p);
    ws.on("server.update", cb);
    return () => ws.off("server.update", cb);
  }, []);

  useEffect(() => {
    let alive = true;
    const tick = () => fetchUsage(getWs(), activeId)
      .then((u) => { if (alive) { setUsage(u); setError(null); setNow(Date.now()); } })
      .catch((e: any) => { if (alive) setError(e?.message ?? String(e)); });
    tick();
    const t = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(t); };
  }, [activeId]);

  const ctx = usage?.context;
  const ctxPct = ctx ? (ctx.used / ctx.window) * 100 : 0;
  const lim = usage?.limits;
  return (
    <footer className="flex h-8 shrink-0 items-center gap-5 overflow-x-auto whitespace-nowrap border-t border-border bg-card px-3 font-mono text-xs">
      {error ? (
        <span role="status" className="text-destructive" title={error}>usage: desconectado ({error})</span>
      ) : (
        <div className={cn("flex items-center gap-6 [&>*]:shrink-0", !usage && "opacity-50")}>
          <span className="flex items-center gap-1.5">
            <span className="text-muted-foreground">ctx{activeId ? ` ${activeId === mainId ? "Manager" : activeId}` : ""}</span>
            {ctx ? (<>
              <Meter pct={ctxPct} />
              <span className={tone(ctxPct)}>{fmtK(ctx.window - ctx.used)} libre</span>
              <span className="text-muted-foreground">({Math.round(ctxPct)}% de {fmtK(ctx.window)})</span>
            </>) : <span className="text-muted-foreground">{activeId ? "sin conversación" : "—"}</span>}
          </span>
          <WorkingNow />
          <WaitingForYou />
          <FeedbackPending />
          <Window label="5h" w={lim?.fiveHour ?? null} now={now} />
          <Window label="semana" w={lim?.weekly ?? null} now={now} />
          {update?.pending && (
            <span className="flex items-center gap-1.5 text-sky-400"
              title={`Se reinicia solo cuando nadie tecleó en una terminal por ${update.idleBefore} s; las conversaciones de claude siguen.`}>
              ⟳ versión nueva: se reinicia cuando dejes de escribir
              <RestartNow />
            </span>)}
          {lim?.error && <span role="alert" className="text-destructive"
            title={`${lim.error} (último OK: ${lim.lastOk ?? "nunca"})`}>⚠ límites: {lim.error}</span>}
        </div>
      )}
    </footer>
  );
}

type Listed = readonly [string, { note: string | null }];
const SKIP_KINDS = ["main", "ide", "recursos"];

/** Cuántas sesiones esperan tu input (su claude terminó el turno o pide un permiso; más las que
 *  quedaron marcadas "esperando tu input" de antes). */
function WaitingForYou() {
  const states = useFolders((s) => s.tree.devStates);
  const sessions = useFolders((s) => s.tree.sessions);
  const byActivity = sessions.filter((x) => !SKIP_KINDS.includes(x.kind ?? "") && isWaiting(x))
    .map((x) => [`s:${x.id}`, { note: x.activity?.note ?? null }] as const);
  const legacy = Object.entries(states ?? {}).filter(([k, v]) => v.block === "waiting-input" && !byActivity.some(([b]) => b === k))
    .map(([k]) => [k, { note: null }] as const);
  return <SessionCounter items={[...byActivity, ...legacy]} one="te espera" many="te esperan" what="te esperan"
    tone="text-orange-300" bg="bg-orange-400/15" dot={["●", "text-orange-500"]} time={waitTime} />;
}

/** Cuántas sesiones tienen su claude trabajando ahora (a la izquierda de «te esperan», igual por dentro). */
function WorkingNow() {
  const sessions = useFolders((s) => s.tree.sessions);
  const items = sessions.filter((x) => !SKIP_KINDS.includes(x.kind ?? "") && x.process === "running" && x.activity?.state === "working")
    .map((x) => [`s:${x.id}`, { note: null }] as const);
  const since = (s?: { activity?: { since?: string | null } | null }) => s?.activity?.since
    ? `desde ${new Date(s.activity.since).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}` : null;
  return <SessionCounter items={items} one="trabajando" many="trabajando" what="trabajando"
    tone="text-sky-300" bg="bg-sky-400/15" dot={["◐", "inline-block leading-none text-sky-400 animate-spin"]} time={since} />;
}

/** Contador de la barra inferior con su lista: hover = se despliega hacia arriba; con el mouse o ↑/↓ te mueves,
 *  click o Enter abre esa sesión (la lista sigue abierta). Sacar el mouse del bloque (contador + lista) la cierra. */
function SessionCounter({ items, one, many, what, tone, bg, dot, time }:
  { items: Listed[]; one: string; many: string; what: string; tone: string; bg: string; dot: [string, string];
    time: (s?: any) => string | null }) {
  const names = useFolders((s) => s.tree.devNames);
  const sessions = useFolders((s) => s.tree.sessions);
  const activeId = useFolders((s) => s.activeId);
  const activePrUrl = useFolders((s) => s.activePrUrl);
  const waiting = items;
  const label = (k: string) => names?.[k] ?? (k.startsWith("s:") ? sessions.find((x) => x.id === k.slice(2))?.title ?? k.slice(2) : k.slice(2));
  const [at, setAt] = useState<DOMRect | null>(null);
  const [idx, setIdx] = useState(0);
  const idxRef = useRef(0); idxRef.current = idx;
  const trigger = useRef<HTMLButtonElement>(null);
  const closing = useRef<number | undefined>(undefined);
  const keys = waiting.map(([k]) => k);
  const go = (k: string) => {
    if (k.startsWith("s:")) useFolders.getState().setActive(k.slice(2));
    else if (k.startsWith("p:")) useFolders.getState().setActivePr(k.slice(2));
  };
  const show = () => {
    window.clearTimeout(closing.current);
    if (at || !trigger.current) return;
    setAt(trigger.current.getBoundingClientRect());
    const cur = keys.findIndex((k) => k === `s:${activeId}` || (!!activePrUrl && k === `p:${activePrUrl}`));
    setIdx(cur >= 0 ? cur : 0);
  };
  // el puntero cruza del contador a la lista: un respiro antes de cerrar
  const hide = () => { window.clearTimeout(closing.current); closing.current = window.setTimeout(() => setAt(null), 150); };
  useEffect(() => () => window.clearTimeout(closing.current), []);
  useEffect(() => { if (at && !waiting.length) setAt(null); }, [at, waiting.length]);
  useEffect(() => {
    if (!at) return;
    // en captura: si el foco está en una terminal, las flechas igual mueven la lista (y no le llegan)
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); e.stopPropagation();
        setIdx((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + keys.length) % keys.length);
      } else if (e.key === "Enter") {
        e.preventDefault(); e.stopPropagation();
        const k = keys[Math.min(idxRef.current, keys.length - 1)]; if (k) go(k);
      } else if (e.key === "Escape") { e.stopPropagation(); setAt(null); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [at, keys.join("|")]);
  if (!waiting.length) return null;
  const sel = Math.min(idx, waiting.length - 1);
  return (<>
    <button ref={trigger} onMouseEnter={show} onMouseLeave={hide} onClick={show}
      title={`Las sesiones ${what === "trabajando" ? "con su claude trabajando" : "que te esperan"}: pasa el mouse para verlas en lista (↑/↓ y Enter para ir)`}
      className={cn("rounded px-1 font-semibold", tone, at && bg)}>
      {waiting.length} {waiting.length === 1 ? one : many}</button>
    {at && createPortal(
      <div role="listbox" aria-label={`Sesiones: ${what}`} onMouseEnter={show} onMouseLeave={hide}
        style={{ left: Math.max(8, Math.min(at.left, window.innerWidth - 368)), bottom: window.innerHeight - at.top }}
        className="fixed z-50 w-[360px] pb-1 font-mono text-xs">
        <div className="max-h-[60vh] overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-xl">
          <div className="px-2 pb-1 pt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {what} · ↑/↓ y Enter, o click</div>
          {waiting.map(([k, v], i) => {
            const s = k.startsWith("s:") ? sessions.find((x) => x.id === k.slice(2)) : undefined;
            const t = time(s);
            const current = k === `s:${activeId}` || (!!activePrUrl && k === `p:${activePrUrl}`);
            return (
              <button key={k} role="option" aria-selected={i === sel} onMouseMove={() => i !== sel && setIdx(i)}
                onClick={() => { setIdx(i); go(k); }}
                title={`Ir a ${label(k)}${v.note ? `\n${v.note}` : ""}`}
                className={cn("flex w-full flex-col items-start gap-0.5 rounded px-2 py-1.5 text-left",
                  i === sel ? "bg-accent text-foreground" : "text-muted-foreground")}>
                <span className="flex w-full items-center gap-1.5">
                  <span aria-hidden className={dot[1]}>{dot[0]}</span>
                  <span className={cn("min-w-0 flex-1 truncate font-semibold", current && "text-primary")}>
                    {s && /^\d+$/.test(s.id) ? `#${s.id} ` : ""}{label(k)}</span>
                  {t && <span className="shrink-0 text-[10px] text-muted-foreground">{t}</span>}
                </span>
                {v.note && <span className="line-clamp-2 pl-4 text-[11px] text-muted-foreground">{v.note}</span>}
              </button>);
          })}
        </div>
      </div>, document.body)}
  </>);
}

/** La revisión nocturna dejó un plan de feedback sin revisar: click = ir a la sesión principal. */
function FeedbackPending() {
  const plans = useFolders((s) => s.tree.feedbackPending);
  const main = useFolders((s) => s.tree.sessions.find((x) => x.kind === "main"));
  const setActive = useFolders((s) => s.setActive);
  if (!plans?.length || !main) return null;
  return (
    <button onClick={() => setActive(main.id)}
      title={`La sesión manager dejó ${plans.length === 1 ? "un plan" : `${plans.length} planes`} de feedback para revisar (${plans.join(", ")}): pídele que te lo muestre y dile qué aplicar`}
      className="rounded border border-primary/60 px-1 text-primary hover:bg-primary/10">
      plan de feedback pendiente</button>);
}

/** «Reiniciar ahora»: si hay sesiones trabajando, reiniciar les corta el turno a medias (lo que estaban
 *  haciendo se pierde; la conversación sigue). Entonces el botón sale como alerta, dice cuáles y pide confirmar. */
function RestartNow() {
  const sessions = useFolders((s) => s.tree.sessions);
  const idx = useFolders((s) => s.tree.devIndex);
  const [confirm, setConfirm] = useState(false);
  const working = sessions.filter((x) => x.process === "running" && x.activity?.state === "working");
  const names = working.map((x) => x.kind === "main" ? "Manager" : x.kind === "ide" ? "IDE" : x.kind === "recursos" ? "Recursos"
    : idx?.[`s:${x.id}`] ? `#${idx[`s:${x.id}`]}` : x.id);
  const restart = () => { setConfirm(false); getWs().request("server.restart", {}).catch(() => {}); };
  if (!working.length)
    return <button title="Reiniciar el IDE ya con la versión nueva (ninguna sesión está trabajando)" onClick={restart}
      className="rounded border border-sky-400/60 px-1 hover:bg-sky-400/10">reiniciar ahora</button>;
  const who = names.join(", ");
  return confirm ? (
    <span className="flex items-center gap-1 text-destructive">
      ¿cortar el turno de {who}?
      <button title="Sí, reiniciar igual" onClick={restart} className="rounded border border-destructive/70 px-1 hover:bg-destructive/10">sí</button>
      <button title="No reiniciar" onClick={() => setConfirm(false)} className="px-1 text-muted-foreground hover:text-foreground">no</button>
    </span>
  ) : (
    <button title={`Reiniciar ahora corta el turno de ${working.length === 1 ? "la sesión que está trabajando" : `las ${working.length} sesiones que están trabajando`} (${who}): lo que estaban haciendo se pierde. Pide confirmar.`}
      onClick={() => setConfirm(true)}
      className="rounded border border-destructive/70 px-1 text-destructive hover:bg-destructive/10">⚠ reiniciar ahora ({working.length} trabajando)</button>
  );
}
