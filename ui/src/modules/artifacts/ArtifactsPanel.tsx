// ui/src/modules/artifacts/ArtifactsPanel.tsx
/** Módulo Artefactos: las páginas de claude.ai que publicó la sesión del desarrollo elegido (el IDE las encuentra
 *  solas en su conversación; también se suman con `ide artifact add`). Cada una con un interruptor para mostrarla o
 *  no en la card. Click: la abre en el navegador. */
import { useState } from "react";
import { ExternalLink, X } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { removeArtifact, setArtifactCard, type Artifact } from "../../transport/folderSessions";
import { openExternal } from "../../lib/openExternal";
import { cn } from "../../lib/utils";

const when = (iso: string) => {
  const d = new Date(iso);
  return isNaN(+d) ? "" : d.toLocaleString("es", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};

function Row({ a, onCard, onRemove }: { a: Artifact; onCard: (show: boolean) => void; onRemove: () => void }) {
  const on = a.card !== false;
  return (
    <div className="group flex items-start gap-1.5 rounded px-1 py-1 hover:bg-accent/50">
      <button onClick={() => openExternal(a.url)} title="Abrir el artefacto en una pestaña nueva del navegador"
        className="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left">
        <span className="line-clamp-2 text-xs font-semibold leading-snug">{a.title ?? a.url}</span>
        {a.description && <span className="line-clamp-2 text-[11px] text-muted-foreground">{a.description}</span>}
        <span className="text-[10px] text-muted-foreground">{when(a.at)}</span>
      </button>
      <button onClick={() => openExternal(a.url)} title="Abrir en una pestaña nueva del navegador"
        className="mt-0.5 shrink-0 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"><ExternalLink size={12} /></button>
      <button onClick={onRemove} title="Sacarlo de este desarrollo (no lo borra de claude.ai)"
        className="mt-0.5 hidden shrink-0 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground group-hover:block"><X size={12} /></button>
      <button role="switch" aria-checked={on} onClick={() => onCard(!on)}
        title={on ? "Se muestra en la card: click para esconderlo ahí (sigue aquí)" : "No se muestra en la card: click para mostrarlo"}
        className={cn("mt-0.5 h-4 w-7 shrink-0 rounded-full border p-[1px] transition-colors", on ? "border-primary bg-primary" : "border-border bg-muted")}>
        <span className={cn("block h-3 w-3 rounded-full bg-background transition-transform", on && "translate-x-3")} />
      </button>
    </div>);
}

export function ArtifactsPanel() {
  const dev = useCurrentDev();
  const list = useFolders((s) => (dev ? s.tree.devArtifacts?.[dev.key] : undefined)) ?? [];
  const [err, setErr] = useState<string | null>(null);
  if (!dev?.session) {
    return <div className="p-3 text-xs text-muted-foreground">Elige un desarrollo con sesión para ver sus artefactos.</div>;
  }
  const sid = dev.session.id;
  const run = (p: Promise<unknown>) => { setErr(null); p.catch((e) => setErr(String(e?.message ?? e))); };
  const items = [...list].sort((a, b) => b.at.localeCompare(a.at));
  return (
    <div className="flex w-full min-w-0 flex-col overflow-y-auto p-2">
      <div className="px-1 text-[10px] uppercase tracking-wide text-muted-foreground">Artefactos ({items.length})</div>
      {!items.length && <div className="px-1 pt-1 text-xs text-muted-foreground">
        Ninguno todavía: los que publique su claude aparecen aquí solos (o súmalo con `ide artifact add`).</div>}
      {items.map((a) => <Row key={a.url} a={a}
        onCard={(show) => run(setArtifactCard(getWs(), sid, a.url, show))}
        onRemove={() => run(removeArtifact(getWs(), sid, a.url))} />)}
      {err && <div className="mt-2 px-1 text-xs text-destructive">{err}</div>}
    </div>);
}
