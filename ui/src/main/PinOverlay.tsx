// ui/src/main/PinOverlay.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { Terminal } from "@xterm/xterm";
import { getWs } from "../transport/wsClient";
import { addPin, sessionMessages } from "../transport/folderSessions";

/** Texto comparable entre la terminal (markdown ya pintado, bordes del TUI, líneas cortadas) y el
 *  transcript (markdown crudo). */
const norm = (s: string) => s.toLowerCase()
  .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
  .replace(/[*`_#>|│┃─━┌┐└┘├┤┬┴┼═║╔╗╚╝●⎿•▪✻✶✳⏺]/g, " ")
  .replace(/\s+/g, " ").trim();

/** 📌 sobre las filas de la tab claude que son parte de un mensaje suyo (y "Pinear selección"): pinea
 *  el mensaje COMPLETO, limpio, sacado del transcript. La terminal no sabe dónde empieza cada mensaje:
 *  se reconoce buscando el texto de la fila en los mensajes recientes. */
export function PinOverlay({ term, sid, devKey, children }:
  { term: Terminal | null; sid: string; devKey: string; children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [msgs, setMsgs] = useState<{ text: string; norm: string }[]>([]);
  const [hover, setHover] = useState<{ top: number; text: string } | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    const load = () => sessionMessages(getWs(), sid, 60)
      .then((r) => setMsgs(r.messages.map((m) => ({ text: m.text, norm: norm(m.text) })))).catch(() => {});
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [sid]);
  const find = useMemo(() => (raw: string): string | null => {
    const n = norm(raw);
    if (n.length < 12) return null;
    return msgs.find((m) => m.norm.includes(n))?.text ?? null;      // los más nuevos primero
  }, [msgs]);
  useEffect(() => {
    if (!term) return;
    const d = term.onSelectionChange(() => setSel(term.getSelection().trim() || null));
    return () => d.dispose();
  }, [term]);
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(null), 2500); return () => clearTimeout(t); }, [note]);
  const frame = useRef(0);
  const onMove = (e: React.MouseEvent) => {
    if (!term?.element || frame.current) return;
    const x = e.clientX, y = e.clientY;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      const screen = term.element?.querySelector(".xterm-screen") as HTMLElement | null;
      if (!screen || !box.current) return;
      const r = screen.getBoundingClientRect();
      if (x < r.left || x > r.right || y < r.top || y > r.bottom) { setHover(null); return; }
      const cell = r.height / term.rows;
      const row = Math.floor((y - r.top) / cell);
      const line = term.buffer.active.getLine(term.buffer.active.viewportY + row)?.translateToString(true) ?? "";
      const text = find(line);
      setHover(text ? { top: r.top - box.current.getBoundingClientRect().top + row * cell, text } : null);
    });
  };
  const pin = (text: string, what: string) =>
    addPin(getWs(), devKey, text, sid).then(() => setNote(`${what} pineado (módulo Pines)`)).catch((e: any) => setNote(`⚠ ${e?.message ?? e}`));
  return (
    <div ref={box} className="relative h-full w-full" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {children}
      {hover && (
        <button title="Pinear este mensaje de claude (completo, al módulo Pines)" aria-label="Pinear mensaje"
          onMouseDown={(e) => e.preventDefault()} onClick={() => { pin(hover.text, "Mensaje"); setHover(null); }}
          style={{ top: hover.top - 2 }}
          className="absolute right-4 z-20 rounded border border-primary/50 bg-card/95 px-1.5 text-xs shadow hover:bg-accent">📌</button>)}
      {sel && (
        <button title="Pinear el mensaje que contiene lo seleccionado (o la selección, si no se reconoce)"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => { const m = find(sel.split("\n").find((l) => norm(l).length >= 12) ?? sel); pin(m ?? sel, m ? "Mensaje" : "Selección"); }}
          className="absolute bottom-3 right-4 z-20 rounded-md border border-primary/50 bg-card/95 px-2 py-1 text-xs shadow hover:bg-accent">
          📌 Pinear selección</button>)}
      {note && <span className="absolute right-4 top-12 z-20 rounded bg-card/95 px-2 py-0.5 text-[11px] text-muted-foreground shadow">{note}</span>}
    </div>
  );
}
