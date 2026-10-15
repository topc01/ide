// ui/src/layout/StatusBar.tsx
import { useEffect, useState } from "react";
import { useFolders } from "../state/folders";
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
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

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
            <span className="text-muted-foreground">ctx{activeId ? ` ${activeId}` : ""}</span>
            {ctx ? (<>
              <Meter pct={ctxPct} />
              <span className={tone(ctxPct)}>{fmtK(ctx.window - ctx.used)} libre</span>
              <span className="text-muted-foreground">({Math.round(ctxPct)}% de {fmtK(ctx.window)})</span>
            </>) : <span className="text-muted-foreground">{activeId ? "sin conversación" : "—"}</span>}
          </span>
          <Window label="5h" w={lim?.fiveHour ?? null} now={now} />
          <Window label="semana" w={lim?.weekly ?? null} now={now} />
          {lim?.error && <span role="alert" className="text-destructive"
            title={`${lim.error} (último OK: ${lim.lastOk ?? "nunca"})`}>⚠ límites: {lim.error}</span>}
        </div>
      )}
    </footer>
  );
}
