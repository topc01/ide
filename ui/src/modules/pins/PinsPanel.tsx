// ui/src/modules/pins/PinsPanel.tsx
import { useEffect, useState } from "react";
import { Check, Copy, Pin as PinIcon, X } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { getWs } from "../../transport/wsClient";
import { listPins, removePin, type Pin } from "../../transport/folderSessions";
import { cn } from "../../lib/utils";

const when = (iso: string | null) => iso ? new Date(iso).toLocaleString("es", { dateStyle: "short", timeStyle: "short" }) : "";

function CopyButton({ text }: { text: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button title="Copiar el texto (markdown, tal cual)" aria-label="Copiar"
      onClick={() => navigator.clipboard.writeText(text).then(() => { setOk(true); setTimeout(() => setOk(false), 1200); })}
      className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
      {ok ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}</button>);
}

/** Texto de un mensaje: recortado (6 líneas) con "ver todo". */
function Body({ text }: { text: string }) {
  const [all, setAll] = useState(false);
  const long = text.length > 400 || text.split("\n").length > 6;
  return (
    <div>
      <p className={cn("whitespace-pre-wrap break-words text-[11px] leading-snug", !all && long && "line-clamp-6")}>{text}</p>
      {long && <button title={all ? "Mostrar menos" : "Mostrar todo"} onClick={() => setAll(!all)}
        className="text-[10px] text-primary hover:underline">{all ? "ver menos" : "ver todo"}</button>}
    </div>);
}

/** Módulo Pines: mensajes de claude guardados (p.ej. un texto para mandar después por un hilo). Se
 *  pinean desde la tab claude (📌 al pasar el mouse sobre una respuesta, o "Pinear selección"). */
export function PinsPanel() {
  const dev = useCurrentDev();
  const [pins, setPins] = useState<Record<string, Pin[]>>({});
  useEffect(() => {
    const ws = getWs();
    listPins(ws).then((r) => setPins(r.pins)).catch(() => {});
    const h = (p: { pins: Record<string, Pin[]> }) => setPins(p.pins);
    ws.on("pins.changed", h);
    return () => ws.off("pins.changed", h);
  }, []);
  if (!dev) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo.</p>;
  const mine = pins[dev.key] ?? [];
  return (
    <div className="flex h-full flex-col overflow-auto pb-3 text-xs">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Pineados</div>
      {mine.length === 0 && <p className="mx-2.5 text-[11px] text-muted-foreground">
        Nada pineado en este desarrollo. En la tab claude, pasa el mouse sobre una respuesta y aprieta 📌 (o selecciona texto y "Pinear selección").</p>}
      {mine.map((p) => (
        <div key={p.id} className="group mx-2 mb-1.5 rounded-md border border-primary/30 bg-card p-2">
          <div className="mb-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
            <PinIcon size={10} className="text-primary" /><span>{when(p.at)}</span>{p.source && <span>· {p.source}</span>}
            <span className="flex-1" />
            <CopyButton text={p.text} />
            <button title="Desfijar" aria-label="Desfijar" onClick={() => removePin(getWs(), dev.key, p.id).catch(() => {})}
              className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"><X size={12} /></button>
          </div>
          <Body text={p.text} />
        </div>))}

    </div>
  );
}
