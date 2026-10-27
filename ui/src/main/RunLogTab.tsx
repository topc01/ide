// ui/src/main/RunLogTab.tsx
import { useEffect, useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { getWs } from "../transport/wsClient";
import { runLog, startRun, stopRun, useRuns } from "../transport/runs";
import { RunState, RunUrls } from "../modules/servers/ServersPanel";
import { Button } from "../components/ui/button";
import { useTheme } from "../state/theme";
import { termTheme } from "./termTheme";

const POLL_MS = 1000;
const b64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

/** Log de un servidor (solo lectura): lo último y después lo nuevo, leyendo el archivo de log. */
export function RunLogTab({ place, repo, name }: { place: string; repo: string; name: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const { state } = useRuns();
  const run = state?.runs.find((r) => r.place === place && r.repo === repo && r.name === name);
  const [err, setErr] = useState<string | null>(null);
  const started = run?.started;

  useEffect(() => {
    const term = new Terminal({
      fontSize: 12, fontFamily: '"JetBrains Mono", ui-monospace, monospace', convertEol: true,
      disableStdin: true, scrollback: 20000, cursorBlink: false,
      theme: termTheme(useTheme.getState().theme, false),
    });
    const unTheme = useTheme.subscribe((s) => { term.options.theme = termTheme(s.theme, false); });
    const fit = new FitAddon();
    term.loadAddon(fit);
    if (ref.current) term.open(ref.current);
    const sync = () => {
      const el = ref.current;
      if (el && (el.offsetWidth === 0 || el.offsetHeight === 0)) return;
      try { fit.fit(); } catch { /* sin layout */ }
    };
    sync();
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(sync);
    if (ro && ref.current) ro.observe(ref.current);
    let offset = -1, stop = false, timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        // seguir leyendo mientras haya más (un log grande llega en pedazos)
        for (let i = 0; i < 8 && !stop; i++) {
          const r = await runLog(getWs(), { place, repo, name }, offset);
          if (r.reset) term.reset();
          const bytes = b64(r.data);
          if (bytes.length) term.write(bytes);
          const more = r.end > offset && bytes.length >= 512 * 1024;
          offset = r.end;
          if (!more) break;
        }
        setErr(null);
      } catch (e: any) { setErr(e?.message ?? String(e)); }
      if (!stop) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => { stop = true; unTheme(); if (timer) clearTimeout(timer); ro?.disconnect(); term.dispose(); };
  }, [place, repo, name, started]);   // corrida nueva → empezar de cero

  const act = (p: Promise<unknown>) => p.catch((e: any) => setErr(e?.message ?? String(e)));
  const alive = run?.state === "running" || run?.state === "stopping";
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1 text-xs">
        <span className="font-mono">{repo}/{name}</span>
        <span className="text-muted-foreground">{place}</span>
        <RunState run={run} />
        <span className="flex gap-1.5"><RunUrls run={run} /></span>
        <span className="flex-1" />
        {err && <span role="alert" className="text-destructive" title={err}>⚠ {err}</span>}
        {alive ? (
          <Button size="sm" variant="ghost" className="h-6 px-2" disabled={run?.state === "stopping"}
            title={`Parar ${name}`} onClick={() => act(stopRun(getWs(), { place, repo, name }))}>
            <Square size={12} /> Parar</Button>
        ) : (
          <Button size="sm" variant="ghost" className="h-6 px-2" title={`Correr ${name} de nuevo (el log se reinicia)`}
            onClick={() => act(startRun(getWs(), { place, repo, name }))}>
            <Play size={12} /> Correr</Button>)}
      </div>
      <div ref={ref} className="min-h-0 flex-1 bg-terminal-bg pl-2" />
    </div>
  );
}
