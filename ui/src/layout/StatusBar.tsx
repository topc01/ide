// ui/src/layout/StatusBar.tsx
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { create } from "zustand";
import { useFolders } from "../state/folders";
import { useStore } from "../state/store";
import { isWaiting, waitTime } from "../modules/sessions/activity";
import { fetchUsage, type Usage, type UsageWindow } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { cn } from "../lib/utils";
import { AttentionDetail } from "./AttentionDetail";

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
  // mismo ancho con o sin datos: nada de la barra se corre
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-muted-foreground">{label}</span><Meter pct={w?.percent ?? 0} />
      <span className={cn("w-9 text-right", w ? tone(w.percent) : "text-muted-foreground")}>{w ? `${Math.round(w.percent)}%` : "—"}</span>
      <span className="w-16 text-muted-foreground" title="Cuánto falta para que se reinicie">{w ? `- ${untilReset(w.resetsAt, now)}` : ""}</span>
    </span>
  );
}

const Sep = () => <span aria-hidden className="text-border">|</span>;

/** Barra inferior, siempre en el mismo orden (nada se corre): contexto de la sesión abierta, ventanas de 5 h y
 *  semanal | contadores fijos (en curso, te esperan, terminaron, decisiones; deshabilitados en 0) y al final los
 *  avisos que van y vienen (plan de feedback, versión nueva, error de límites). */
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
        <div className={cn("flex items-center gap-3 [&>*]:shrink-0", !usage && "opacity-50")}>
          <span className="flex items-center gap-1.5"
            title={ctx ? `Contexto de la sesión ${activeId === mainId ? "Manager" : activeId}: ${fmtK(ctx.window - ctx.used)} libres de ${fmtK(ctx.window)}` : "Contexto de la sesión abierta"}>
            <span className="text-muted-foreground">sesión</span>
            <Meter pct={ctxPct} />
            <span className={cn("w-9 text-right", ctx ? tone(ctxPct) : "text-muted-foreground")}>{ctx ? `${Math.round(ctxPct)}%` : "—"}</span>
          </span>
          <Sep />
          <Window label="5h" w={lim?.fiveHour ?? null} now={now} />
          <Sep />
          <Window label="semana" w={lim?.weekly ?? null} now={now} />
          <Sep />
          <WorkingNow />
          <WaitingForYou />
          <FinishedNow />
          <Decisions />
          <FeedbackPending />
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

type Listed = readonly [string, { note: string | null; reason?: string | null }];

/** Por qué te espera, en la card de la lista (el detalle dice el resto). */
const WAIT_REASON: Record<string, [string, string]> = {
  permission: ["permiso", "border-red-400/70 text-red-300"],
  question: ["pregunta", "border-amber-400/70 text-amber-300"],
  login: ["login", "border-red-400/70 text-red-300"],
  turn: ["terminó", "border-border text-muted-foreground"],
  interrupt: ["interrumpida", "border-violet-400/60 text-violet-300"],
  idle: ["inactiva", "border-border text-muted-foreground"],
  launch: ["recién abierta", "border-border text-muted-foreground"],
};
const SKIP_KINDS = ["main", "ide", "recursos", "plugins"];

/** Lo que necesita tu respuesta para seguir: pide un permiso o te hizo una pregunta. */
const BLOCKED = ["permission", "question", "login"];

/** Las sesiones paradas esperando algo de ti: «te esperan» = bloqueadas (permiso o pregunta; más las marcadas
 *  "esperando tu input" de antes); «terminaron» = el resto (terminó el turno, la interrumpiste, inactiva, recién
 *  abierta). */
function useWaiting() {
  const states = useFolders((s) => s.tree.devStates);
  const sessions = useFolders((s) => s.tree.sessions);
  const all = sessions.filter((x) => !SKIP_KINDS.includes(x.kind ?? "") && isWaiting(x))
    .map((x) => [`s:${x.id}`, { note: x.activity?.note ?? null, reason: x.activity?.reason ?? null }] as const);
  const legacy = Object.entries(states ?? {}).filter(([k, v]) => v.block === "waiting-input" && !all.some(([b]) => b === k))
    .map(([k]) => [k, { note: null, reason: null }] as const);
  return {
    blocked: [...all.filter(([, v]) => BLOCKED.includes(v.reason ?? "")), ...legacy],
    finished: all.filter(([, v]) => !BLOCKED.includes(v.reason ?? "")),
  };
}

function WaitingForYou() {
  return <SessionCounter items={useWaiting().blocked} one="te espera" many="te esperan" what="te esperan" />;
}

function FinishedNow() {
  return <SessionCounter items={useWaiting().finished} one="terminó" many="terminaron" what="terminaron" />;
}

/** Cuántas sesiones tienen su claude trabajando ahora (a la izquierda de «te esperan», igual por dentro). */
function WorkingNow() {
  const sessions = useFolders((s) => s.tree.sessions);
  const items = sessions.filter((x) => !SKIP_KINDS.includes(x.kind ?? "") && x.process === "running" && !x.frozen && x.activity?.state === "working")
    .map((x) => [`s:${x.id}`, { note: null }] as const);
  const since = (s?: { activity?: { since?: string | null } | null }) => s?.activity?.since
    ? `desde ${new Date(s.activity.since).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })}` : null;
  return <SessionCounter items={items} one="en curso" many="en curso" what="trabajando"
    tone="text-sky-300" bg="bg-sky-400/15" dot={["◐", "inline-block leading-none text-sky-400 animate-spin"]} time={since} />;
}

/** Lo que ocupa en pantalla cada lista abierta de la barra (con su detalle): otra lista que se abre se corre al
 *  costado en vez de taparla. */
const useOpenLists = create<{ spans: Record<string, [number, number]>; set: (k: string, v: [number, number] | null) => void }>((set) => ({
  spans: {},
  set: (k, v) => set((st) => {
    const spans = { ...st.spans };
    if (v) spans[k] = v; else delete spans[k];
    return { spans };
  }),
}));

/** Contador de la barra inferior con su lista de cards (número y nombre). Hover = se despliega hacia arriba;
 *  click en el contador = queda fija hasta Esc. Hover en una card = su detalle al lado mientras el mouse está ahí;
 *  click = el detalle queda fijo y ↑/↓ lo cambia a la sesión de arriba/abajo. Enter (o «ir a la sesión») abre la
 *  sesión. Esc cierra todo (dentro del campo para responder, primero sale del campo). */
function SessionCounter({ items, one, many, what }:
  { items: Listed[]; one: string; many: string; what: "te esperan" | "trabajando" | "terminaron"; tone?: string; bg?: string;
    dot?: [string, string]; time?: (s?: any) => string | null }) {
  const names = useFolders((s) => s.tree.devNames);
  const sessions = useFolders((s) => s.tree.sessions);
  const devStates = useFolders((s) => s.tree.devStates);
  const activeId = useFolders((s) => s.activeId);
  const activePrUrl = useFolders((s) => s.activePrUrl);
  const waiting = items;
  const working = what === "trabajando";
  const tone = working ? "text-sky-300" : what === "terminaron" ? "text-muted-foreground" : "text-orange-300";
  const bg = working ? "bg-sky-400/15" : what === "terminaron" ? "bg-muted" : "bg-orange-400/15";
  const border = working ? "border-sky-400/60" : what === "terminaron" ? "border-border" : "border-orange-400/70";
  const label = (k: string) => names?.[k] ?? (k.startsWith("s:") ? sessions.find((x) => x.id === k.slice(2))?.title ?? k.slice(2) : k.slice(2));
  const [at, setAt] = useState<DOMRect | null>(null);
  const [pinned, setPinned] = useState(false);            // la lista, fija (click en el contador)
  const [detailPinned, setDetailPinned] = useState(false); // el detalle, fijo (click en una card)
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const spans = useOpenLists((st) => st.spans);
  const setSpan = useOpenLists((st) => st.set);
  const clickTimer = useRef<number | undefined>(undefined);
  const spanRef = useRef<[number, number] | null>(null);
  // después de cada render: anota lo que ocupa esta lista (solo si cambió, si no se re-renderizan en loop)
  useEffect(() => {
    const cur = useOpenLists.getState().spans[what] ?? null, v = spanRef.current;
    if (JSON.stringify(cur) !== JSON.stringify(v)) setSpan(what, v);
  });
  useEffect(() => () => setSpan(what, null), []);
  const [idx, setIdx] = useState(0);
  const idxRef = useRef(0); idxRef.current = idx;
  const trigger = useRef<HTMLButtonElement>(null);
  const closing = useRef<number | undefined>(undefined);
  const hoverOff = useRef<number | undefined>(undefined);
  const keys = waiting.map(([k]) => k);
  const persistent = pinned || detailPinned;
  const go = (k: string) => {
    if (k.startsWith("s:")) useFolders.getState().setActive(k.slice(2));
    else if (k.startsWith("p:")) useFolders.getState().setActivePr(k.slice(2));
  };
  const closeAll = () => { setAt(null); setPinned(false); setDetailPinned(false); setHoverKey(null); };
  const show = () => {
    window.clearTimeout(closing.current);
    if (at || !trigger.current) return;
    setAt(trigger.current.getBoundingClientRect());
    const cur = keys.findIndex((k) => k === `s:${activeId}` || (!!activePrUrl && k === `p:${activePrUrl}`));
    setIdx(cur >= 0 ? cur : 0);
  };
  // el puntero cruza del contador a la lista (o al detalle): un respiro antes de cerrar
  const hide = () => {
    if (persistent) return;
    window.clearTimeout(closing.current);
    closing.current = window.setTimeout(() => { setAt(null); setHoverKey(null); }, 150);
  };
  const hoverIn = (k: string) => { window.clearTimeout(hoverOff.current); setHoverKey(k); };
  const hoverOut = () => { window.clearTimeout(hoverOff.current); hoverOff.current = window.setTimeout(() => setHoverKey(null), 120); };
  useEffect(() => () => { window.clearTimeout(closing.current); window.clearTimeout(hoverOff.current); }, []);
  useEffect(() => { if (at && !waiting.length) closeAll(); }, [at, waiting.length]);
  useEffect(() => {
    if (!at) return;
    // en captura: si el foco está en una terminal, las flechas igual mueven la lista (y no le llegan).
    // En el campo para responder del detalle, las teclas son del campo.
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT") && t.closest("[data-attention]")) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); e.stopPropagation();
        // el detalle sigue a la selección (antes se quedaba en la sesión que tenía el mouse encima)
        setIdx((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + keys.length) % keys.length);
        setDetailPinned(true); setPinned(true);
      } else if (e.key === "Enter") {
        e.preventDefault(); e.stopPropagation();
        const k = keys[Math.min(idxRef.current, keys.length - 1)]; if (k) go(k);
      } else if (e.key === "Escape") { e.stopPropagation(); closeAll(); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [at, keys.join("|")]);
  if (!waiting.length) {
    spanRef.current = null;
    return <button disabled
      className="cursor-default rounded border border-border px-1.5 text-muted-foreground opacity-60">0 {many}</button>;
  }
  const sel = Math.min(idx, waiting.length - 1);
  const shown = detailPinned ? keys[sel] : hoverKey;
  const detailW = 500;
  // la lista y su detalle van juntos (el detalle a la derecha); si otra lista abierta ocupa ese lugar, se corre
  const blockW = 368 + (shown ? detailW : 0);
  const W = window.innerWidth;
  const others = Object.entries(spans).filter(([k]) => k !== what).map(([, v]) => v);
  const fits = (l: number) => l >= 8 && l + blockW <= W - 8 && !others.some(([a, b]) => l < b + 8 && l + blockW > a - 8);
  const start = at ? Math.max(8, Math.min(at.left, W - blockW - 8)) : 0;
  const listLeft = !at ? 0 : fits(start) ? start
    : [...others.map(([, b]) => b + 8), ...others.map(([a]) => a - 8 - blockW)].filter(fits)
      .sort((x, y) => Math.abs(x - start) - Math.abs(y - start))[0] ?? start;
  const detailLeft = listLeft + 368;
  const shownSid = shown?.startsWith("s:") ? shown.slice(2) : null;
  spanRef.current = at ? [listLeft, listLeft + blockW] : null;
  return (<>
    <button ref={trigger} onMouseEnter={show} onMouseLeave={hide}
      onClick={() => { show(); setPinned(true); }}
      // sin tooltip: tapaba la barra y la lista (el encabezado de la lista ya explica cómo se usa)
      className={cn("rounded border px-1.5 font-semibold hover:brightness-125", tone, border, (at || pinned) && bg)}>
      {waiting.length} {waiting.length === 1 ? one : many}</button>
    {at && createPortal(
      <div data-attention onMouseEnter={show} onMouseLeave={hide}>
        <div role="listbox" aria-label={`Sesiones: ${what}`}
          style={{ left: listLeft, bottom: window.innerHeight - at.top }}
          className="fixed z-50 w-[360px] pb-1 font-mono text-xs">
          <div className="max-h-[70vh] overflow-y-auto rounded-md border border-border bg-popover p-1.5 shadow-xl">
            <div className="px-1 pb-1.5 pt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              {what}{persistent ? " · fija: Esc cierra" : ""} · click abre · doble click fija · ↑/↓</div>
            <div className="flex flex-col gap-1">
              {waiting.map(([k, v], i) => {
                // terminó y su PR espera a los revisores: eso es lo que la frena, no «terminó»
                const inReview = !working && !BLOCKED.includes(v.reason ?? "") && devStates?.[k]?.phase === "in-review";
                const why = working ? null : inReview ? ["esperando revisión", "border-sky-400/60 text-sky-300"] as [string, string]
                  : WAIT_REASON[v.reason ?? ""] ?? null;
                const s = k.startsWith("s:") ? sessions.find((x) => x.id === k.slice(2)) : undefined;
                const current = k === `s:${activeId}` || (!!activePrUrl && k === `p:${activePrUrl}`);
                const isShown = k === shown;
                return (
                  <button key={k} role="option" aria-selected={i === sel}
                    onMouseEnter={() => hoverIn(k)} onMouseLeave={hoverOut}
                    onMouseMove={() => i !== sel && !detailPinned && setIdx(i)}
                    // un click abre la sesión; doble click deja fijos la lista y el detalle
                    onClick={(e) => {
                      window.clearTimeout(clickTimer.current);
                      if (e.detail > 1) return;
                      clickTimer.current = window.setTimeout(() => { closeAll(); go(k); }, 250);
                    }}
                    onDoubleClick={() => { window.clearTimeout(clickTimer.current); setIdx(i); setPinned(true); setDetailPinned(true); }}
                    // sin title: el tooltip tapaba las cards de abajo (el encabezado de la lista ya explica)
                    className={cn("flex w-full items-start gap-2 rounded border px-2 py-1.5 text-left",
                      i === sel ? "border-primary/60 bg-accent text-foreground" : "border-border bg-background/40 text-muted-foreground hover:text-foreground",
                      isShown && detailPinned && "ring-1 ring-primary")}>
                    {s && /^\d+$/.test(s.id) && <span className={cn("shrink-0 font-semibold", tone)}>#{s.id}</span>}
                    <span className={cn("min-w-0 flex-1 font-semibold leading-snug line-clamp-2", current && "text-primary")}>{label(k)}</span>
                    {why && <span className={cn("shrink-0 rounded border px-1 text-[10px] leading-4", why[1])}>{why[0]}</span>}
                  </button>);
              })}
            </div>
          </div>
        </div>
        {shownSid && (
          <div data-float onMouseEnter={() => shown && hoverIn(shown)} onMouseLeave={hoverOut}
            style={{ left: detailLeft, bottom: window.innerHeight - at.top, width: detailW }}
            className="fixed z-50 pb-1">
            <AttentionDetail sid={shownSid} title={label(shown!)} mode={working ? "working" : "waiting"}
              pinned={detailPinned} onGo={() => go(shown!)} />
          </div>
        )}
      </div>, document.body)}
  </>);
}

/** «N bloqueantes» (rojo): decisiones y pendientes que frenan a los desarrollos (módulo Bloqueantes); click lo abre.
 *  Es lo que hay que bajar. */
function Decisions() {
  const n = useFolders((s) => s.tree.later?.length ?? 0);
  const { activePanel, setActivePanel, innerSidebarOpen, toggleInnerSidebar } = useStore();
  return (
    <button disabled={!n} onClick={() => { if (activePanel !== "later") setActivePanel("later"); if (!innerSidebarOpen) toggleInnerSidebar(); }}
      className="rounded border border-red-400/70 px-1.5 font-semibold text-red-300 hover:bg-red-400/10 disabled:border-border disabled:font-normal disabled:cursor-default disabled:text-muted-foreground disabled:opacity-60 disabled:hover:bg-transparent">
      {n} {n === 1 ? "bloqueante" : "bloqueantes"}</button>);
}

/** La revisión semanal dejó un plan de feedback sin revisar: click = ir a la sesión principal. */
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
  const working = sessions.filter((x) => x.process === "running" && !x.frozen && x.activity?.state === "working");
  const names = working.map((x) => x.kind === "main" ? "Manager" : x.kind === "ide" ? "IDE" : x.kind === "recursos" ? "Recursos" : x.kind === "plugins" ? "Plugins"
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
