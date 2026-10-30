import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { replayTerminal, subscribeTerminal, writeTerminal, resizeTerminal } from "../transport/terminalChannel";
import { getWs } from "../transport/wsClient";
import { useFolders } from "../state/folders";
import { useTheme } from "../state/theme";
import { termTheme } from "./termTheme";
import { PATH_RE } from "./pathLinks";

/** Terminales vivas en memoria, por id: al cambiar de desarrollo no se descartan (siguen recibiendo
 *  la salida de fondo), así volver a una es instantáneo. La primera vez cuesta el replay (todo lo que
 *  imprimió el proceso, hasta 2 MB que xterm tiene que procesar). Se liberan las menos usadas. */
interface Live {
  term: Terminal; fit: FitAddon; wrap: HTMLDivElement; last: string; used: number;
  dispose: () => void;
  onPath?: (raw: string) => (() => void) | null;  // una ruta de la línea → cómo abrirla (null: no es link)
}
const live = new Map<string, Live>();
const MAX_LIVE = 10;

function create(id: string): Live {
  const term = new Terminal({
    fontSize: 12, fontFamily: '"JetBrains Mono", ui-monospace, monospace',
    theme: termTheme(useTheme.getState().theme),
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  const wrap = document.createElement("div");
  wrap.className = "h-full w-full";
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
  const input = term.onData((d) => writeTerminal(getWs(), id, d));
  // rutas clickeables (las que la tab sepa abrir: `onPath`, p.ej. adjuntos y archivos de la sesión)
  const links = term.registerLinkProvider({
    provideLinks(y, cb) {
      const line = term.buffer.active.getLine(y - 1)?.translateToString(true) ?? "";
      const found = [];
      for (const m of line.matchAll(PATH_RE)) {
        const text = m[0].replace(/[.,;)]+$/, "");     // el punto final de la oración no es parte de la ruta
        const go = entry.onPath?.(text);
        if (!go) continue;
        const x = (m.index ?? 0) + 1;
        found.push({ text, range: { start: { x, y }, end: { x: x + text.length - 1, y } },
          decorations: { underline: true, pointerCursor: true }, activate: () => go() });
      }
      cb(found.length ? found : undefined);
    },
  });
  const entry: Live = {
    term, fit, wrap, last: "", used: Date.now(),
    dispose: () => { links.dispose(); input.dispose(); unsubscribe(); term.dispose(); wrap.remove(); live.delete(id); },
  };
  live.set(id, entry);
  return entry;
}

// Al cortarse la conexión con el server se pierde lo que se imprimió mientras tanto: las que no están
// a la vista se descartan (la próxima vez se abren con replay). La visible sigue (puede faltarle lo de
// ese corte; cambiar de desarrollo y volver la rearma).
useFolders.subscribe((s, prev) => {
  if (s.connected && !prev.connected) {
    for (const e of [...live.values()]) if (!e.wrap.isConnected) e.dispose();
  }
});

// al cambiar el tema del IDE, las terminales vivas cambian de colores
useTheme.subscribe((s, prev) => {
  if (s.theme !== prev.theme) for (const e of live.values()) e.term.options.theme = termTheme(s.theme);
});

/** Libera las menos usadas que no estén a la vista (sobre MAX_LIVE). */
function trim() {
  const idle = [...live.entries()].filter(([, e]) => !e.wrap.isConnected).sort((a, b) => a[1].used - b[1].used);
  while (live.size > MAX_LIVE && idle.length) idle.shift()![1].dispose();
}

/** `onTerm`: para quien necesite leer la terminal (p.ej. pinear mensajes desde la tab claude). */
/** `onPath`: qué rutas de la salida son links (p.ej. los adjuntos y archivos que menciona claude). */
export function TerminalTab({ id, onTerm, onPath }: { id: string; onTerm?: (term: Terminal | null) => void;
  onPath?: (raw: string) => (() => void) | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { const e = live.get(id); if (e) e.onPath = onPath; });
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    const e = live.get(id) ?? create(id);
    e.onPath = onPath;
    e.used = Date.now();
    host.appendChild(e.wrap);
    if (!e.term.element) e.term.open(e.wrap);
    // Solo se avisa al PTY si está visible y el tamaño cambió: cada resize hace que `claude`
    // borre y reimprima toda la conversación (parece que la sesión arrancó de nuevo), y oculta
    // (`hidden`, 0x0) el fit daría un tamaño basura.
    const sync = () => {
      if (host.offsetWidth === 0 || host.offsetHeight === 0) return;
      try { e.fit.fit(); } catch { /* jsdom / sin layout */ }
      const size = `${e.term.cols}x${e.term.rows}`;
      if (size === e.last) return;
      e.last = size;
      resizeTerminal(getWs(), id, e.term.cols, e.term.rows);
    };
    sync();
    e.term.refresh(0, e.term.rows - 1);         // volvió a la vista: repintar lo que llegó de fondo
    // re-ajustar al mostrarse (estaba `hidden` → 0x0) o al cambiar el tamaño del panel
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(sync);
    ro?.observe(host);
    onTerm?.(e.term);
    trim();
    return () => { onTerm?.(null); ro?.disconnect(); e.wrap.remove(); e.used = Date.now(); trim(); };
  }, [id]);
  return <div ref={ref} className="h-full w-full bg-terminal-bg" />;
}
