// ui/src/modules/later/LaterPanel.tsx
/** Módulo Decisiones: lo que tienes que decidir o conversar con alguien, de todos los desarrollos. Cada una es una
 *  pregunta de una línea, con el artefacto del análisis (opcional: click en la pregunta lo abre) y con quién
 *  conversarla. Agrupadas por desarrollo (el actual primero) o por persona. Las deja la sesión (`ide later add`)
 *  o tú desde acá; la respuesta se le manda a la sesión. */
import { useState } from "react";
import { Check, ExternalLink, Send, X } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { laterAdd, laterAnswer, laterDismiss, laterResolve, type LaterItem } from "../../transport/folderSessions";
import { Button } from "../../components/ui/button";
import { devKeys, devName } from "../sessions/desarrollos";
import { ago } from "../sessions/devStates";
import { openExternal } from "../../lib/openExternal";
import { cn } from "../../lib/utils";

const field = "w-full rounded border border-border bg-background px-1.5 py-1 text-[11px] text-foreground outline-none focus:border-primary";

/** Nombre corto de un desarrollo por su clave: "#12 nombre". */
function useDevLabel() {
  const tree = useFolders((s) => s.tree);
  return (key: string) => {
    const n = tree.devIndex?.[key];
    const sid = key.startsWith("s:") ? key.slice(2) : null;
    const name = devName(tree.devNames, key) ?? (sid ? tree.sessions.find((s) => s.id === sid)?.title : null)
      ?? key.replace(/^p:https:\/\/github\.com\/[^/]+\/([^/]+)\/pull\/(\d+)$/, "$1#$2");
    return `${n !== undefined ? `#${n} ` : ""}${name ?? key}`;
  };
}

/** Una decisión: la pregunta (click: abre el artefacto, o la sesión si no tiene), con quién y de qué desarrollo. */
function Item({ it, devLabel }: { it: LaterItem; devLabel?: string }) {
  const [answer, setAnswer] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const toSession = it.key.startsWith("s:");
  const send = () => {
    if (!answer?.trim()) return;
    setBusy(true); setMsg(null);
    laterAnswer(getWs(), it.id, answer.trim()).catch((e: any) => { setMsg(`⚠ ${e?.message ?? String(e)}`); setBusy(false); });
  };
  const open = () => {
    if (it.artifact) openExternal(it.artifact);
    else if (toSession) useFolders.getState().setActive(it.key.slice(2));
  };
  return (
    <div className="mx-2 mb-1.5 rounded-md border border-border bg-card p-2">
      <div className="mb-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
        {it.with && <span className="rounded border border-sky-400/60 px-1 font-semibold text-sky-300">con {it.with}</span>}
        {devLabel && <span className="truncate">{devLabel}</span>}
        <span className="shrink-0">· hace {ago(it.created)}</span>
        <span className="flex-1" />
        <button title="Resuelto: cerrarla sin mandarle nada a la sesión (se resolvió en el chat)" aria-label="Resuelto"
          onClick={() => laterResolve(getWs(), it.id).catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`))}
          className="rounded p-0.5 hover:bg-accent hover:text-emerald-400"><Check size={12} /></button>
        <button title="Descartar (sin responder)" aria-label="Descartar"
          onClick={() => laterDismiss(getWs(), it.id).catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`))}
          className="rounded p-0.5 hover:bg-accent hover:text-foreground"><X size={12} /></button>
      </div>
      <button onClick={open} title={it.artifact ? "Abrir el análisis (artefacto) en el navegador" : toSession ? "Ir a la sesión" : ""}
        className="block w-full text-left text-[12px] font-semibold leading-snug hover:text-primary">
        {it.text}{it.artifact && <ExternalLink size={11} className="ml-1 inline align-[-1px] text-muted-foreground" />}</button>
      {it.context && (more
        ? <p className="mt-0.5 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{it.context}</p>
        : <button onClick={() => setMore(true)} title="Ver el contexto que dejó la sesión"
            className="mt-0.5 text-[10px] text-muted-foreground hover:text-foreground">contexto…</button>)}
      {answer === null ? (
        <button title={toSession ? "Responder: la respuesta se le manda a la sesión" : "Anotar la respuesta"}
          onClick={() => setAnswer("")} className="mt-1 block text-[11px] text-primary hover:underline">Responder</button>
      ) : (
        <div className="mt-1.5">
          <textarea autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)} rows={3}
            placeholder="qué se decidió" aria-label="Respuesta"
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); if (e.key === "Escape") setAnswer(null); }}
            className={cn(field, "resize-y")} />
          <div className="mt-1 flex items-center gap-1">
            <Button size="sm" className="h-6 gap-1 px-2 text-[11px]" disabled={busy || !answer.trim()} onClick={send}
              title={toSession ? "Mandar la respuesta a la sesión (⌘Enter)" : "Guardar la respuesta (⌘Enter)"}>
              <Send size={11} />{toSession ? "Mandar a la sesión" : "Guardar"}</Button>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" title="Cancelar" onClick={() => setAnswer(null)}>Cancelar</Button>
          </div>
        </div>)}
      {msg && <p role="alert" className="mt-1 text-[11px] text-destructive">{msg}</p>}
    </div>);
}

export function LaterPanel() {
  const dev = useCurrentDev();
  const items = useFolders((s) => s.tree.later) ?? [];
  const label = useDevLabel();
  const [by, setBy] = useState<"dev" | "who">("dev");
  const [text, setText] = useState("");
  const [who, setWho] = useState("");
  const [art, setArt] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const mineKeys = dev ? devKeys(dev.key, dev.prs) : [];
  const groupOf = (it: LaterItem) => by === "dev" ? it.key : (it.with ?? "");
  const groups = new Map<string, LaterItem[]>();
  for (const it of items) groups.set(groupOf(it), [...(groups.get(groupOf(it)) ?? []), it]);
  const order = [...groups.keys()].sort((a, b) => by === "dev"
    ? Number(mineKeys.includes(b)) - Number(mineKeys.includes(a))
    : (a === "" ? 1 : b === "" ? -1 : groups.get(b)!.length - groups.get(a)!.length));
  const add = () => {
    if (!dev || !text.trim()) return;
    setErr(null);
    laterAdd(getWs(), dev.key, text.trim(), null, { with: who.trim() || null, artifact: art.trim() || null })
      .then(() => { setText(""); setWho(""); setArt(""); }).catch((e: any) => setErr(e?.message ?? String(e)));
  };
  const here = items.filter((it) => mineKeys.includes(it.key)).length;
  return (
    <div className="flex h-full flex-col overflow-auto pb-3 text-xs">
      <div className="mx-2.5 mt-2.5 flex items-baseline gap-1.5">
        <span className="font-mono text-sm font-bold text-primary">{items.length}</span>
        <span className="flex-1 text-muted-foreground">{items.length === 1 ? "decisión" : "decisiones"}
          {dev && items.length > 0 ? ` · ${here} de este desarrollo` : ""}</span>
        {(["dev", "who"] as const).map((k) => (
          <button key={k} onClick={() => setBy(k)} title={k === "dev" ? "Agrupar por desarrollo" : "Agrupar por con quién conversarlas"}
            className={cn("rounded px-1 text-[10px]", by === k ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
            {k === "dev" ? "desarrollo" : "persona"}</button>))}
      </div>
      {dev && (
        <div className="mx-2.5 mt-2.5 space-y-1">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Agregar a {label(dev.key)}</div>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="la pregunta" aria-label="Pregunta"
            onKeyDown={(e) => { if (e.key === "Enter") add(); }} className={field} />
          <div className="flex gap-1">
            <input value={who} onChange={(e) => setWho(e.target.value)} placeholder="con quién (opcional)" aria-label="Con quién"
              onKeyDown={(e) => { if (e.key === "Enter") add(); }} className={field} />
            <input value={art} onChange={(e) => setArt(e.target.value)} placeholder="link del artefacto (opcional)" aria-label="Artefacto"
              onKeyDown={(e) => { if (e.key === "Enter") add(); }} className={field} />
          </div>
          <Button size="sm" className="h-6 px-2 text-[11px]" disabled={!text.trim()} onClick={add}
            title="Dejar esta decisión en el desarrollo actual">Agregar</Button>
          {err && <p role="alert" className="text-[11px] text-destructive">{err}</p>}
        </div>)}
      {!items.length && <p className="mx-2.5 mt-3 text-[11px] text-muted-foreground">
        Nada por decidir. Las sesiones dejan acá lo que tienes que decidir o conversar (`ide later add`).</p>}
      {order.map((g) => (
        <div key={g || "-"} className="mt-3">
          <div className={cn("mx-2.5 mb-1 truncate text-[10px] font-semibold uppercase tracking-wide",
            by === "dev" && mineKeys.includes(g) ? "text-primary" : "text-muted-foreground")}>
            {by === "dev" ? label(g) : g ? `con ${g}` : "sin persona"} · {groups.get(g)!.length}</div>
          {groups.get(g)!.map((it) => <Item key={it.id} it={it} devLabel={by === "who" ? label(it.key) : undefined} />)}
        </div>))}
    </div>);
}
