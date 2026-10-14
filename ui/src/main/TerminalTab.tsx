import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { subscribeTerminal, writeTerminal, resizeTerminal } from "../transport/terminalChannel";
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
    try { fit.fit(); } catch { /* jsdom */ }
    resizeTerminal(getWs(), id, term.cols, term.rows);
    const unsubscribe = subscribeTerminal(getWs(), id,
      (bytes) => term.write(bytes),
      () => term.write("\r\n[proceso terminado]\r\n"));
    term.onData((d) => writeTerminal(getWs(), id, d));
    // re-ajustar al mostrarse (estaba `hidden` → 0x0) o al cambiar el tamaño del panel
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      try { fit.fit(); } catch { /* sin layout */ }
      resizeTerminal(getWs(), id, term.cols, term.rows);
    });
    if (ro && ref.current) ro.observe(ref.current);
    return () => { ro?.disconnect(); unsubscribe(); term.dispose(); };
  }, [id]);
  return <div ref={ref} className="h-full w-full bg-terminal-bg" />;
}
