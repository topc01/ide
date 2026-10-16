import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { replayTerminal, subscribeTerminal, writeTerminal, resizeTerminal } from "../transport/terminalChannel";
import { getWs } from "../transport/wsClient";

export function TerminalTab({ id }: { id: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const term = new Terminal({
      fontSize: 12, fontFamily: '"JetBrains Mono", ui-monospace, monospace',
      theme: { background: "#0f0e0c", foreground: "#f0ece4", cursor: "#e0863f" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    if (ref.current) term.open(ref.current);
    // Solo se avisa al PTY si está visible y el tamaño cambió: cada resize hace que `claude`
    // borre y reimprima toda la conversación (parece que la sesión arrancó de nuevo), y oculta
    // (`hidden`, 0x0) el fit daría un tamaño basura.
    let last = "";
    const sync = () => {
      const el = ref.current;
      if (el && (el.offsetWidth === 0 || el.offsetHeight === 0)) return;
      try { fit.fit(); } catch { /* jsdom / sin layout */ }
      const size = `${term.cols}x${term.rows}`;
      if (size === last) return;
      last = size;
      resizeTerminal(getWs(), id, term.cols, term.rows);
    };
    sync();
    // Al abrir con el proceso ya corriendo: primero lo que ya imprimió (replay) y después solo lo
    // nuevo. `end` = bytes impresos en total: lo que llega antes del replay y ya está incluido se
    // descarta, sin perder ni duplicar.
    let replayed: number | null = null;
    const queued: [Uint8Array, number | undefined][] = [];
    const writeAfter = (bytes: Uint8Array, end?: number) => {
      if (end === undefined || replayed === null) { term.write(bytes); return; }
      const start = end - bytes.length;
      if (end <= replayed) return;
      term.write(start >= replayed ? bytes : bytes.subarray(replayed - start));
      replayed = end;
    };
    let ready = false;
    const unsubscribe = subscribeTerminal(getWs(), id,
      (bytes, end) => { if (ready) writeAfter(bytes, end); else queued.push([bytes, end]); },
      () => { /* el server ya escribió "[terminó: exit N]" en la salida */ });
    replayTerminal(getWs(), id)
      .then(({ bytes, end }) => { term.write(bytes); replayed = end; })
      .catch(() => { /* server viejo sin replay: solo lo nuevo */ })
      .finally(() => { ready = true; queued.splice(0).forEach(([b, e]) => writeAfter(b, e)); });
    term.onData((d) => writeTerminal(getWs(), id, d));
    // re-ajustar al mostrarse (estaba `hidden` → 0x0) o al cambiar el tamaño del panel
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(sync);
    if (ro && ref.current) ro.observe(ref.current);
    return () => { ro?.disconnect(); unsubscribe(); term.dispose(); };
  }, [id]);
  return <div ref={ref} className="h-full w-full bg-terminal-bg" />;
}
