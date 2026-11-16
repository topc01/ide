// ui/src/modules/later/LaterPanel.tsx
/** Módulo Bloqueantes: lo que frena a los desarrollos. Dos tipos: **decisión** (la decides tú o la conversas con
 *  alguien) y **pendiente** (algo que se espera de alguien). Cada uno con con quién y, opcional, el artefacto del
 *  análisis (click en el texto lo abre). Si «bloquea el desarrollo», éste pasa a Bloqueado hasta cerrarlo. Los dejan
 *  las sesiones (`ide later add`) o tú con «+ Nuevo bloqueante»; la respuesta se le manda a la sesión. */
import { useEffect, useRef, useState } from "react";
import { useLaterFocus } from "./focus";
import { Check, CircleHelp, ExternalLink, Hourglass, Pencil, Plus, Send, X } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { laterAdd, laterAnswer, laterDismiss, laterResolve, laterUpdate, type LaterItem } from "../../transport/folderSessions";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { devKeys, devName } from "../sessions/desarrollos";
import { ago } from "../sessions/devStates";
import { openExternal } from "../../lib/openExternal";
import { cn } from "../../lib/utils";

const field = "w-full rounded border border-border bg-background px-1.5 py-1 text-[12px] text-foreground outline-none focus:border-primary";
type Kind = "decision" | "pending";
const KIND: Record<Kind, { label: string; Icon: typeof CircleHelp; tone: string }> = {
  decision: { label: "Decisión", Icon: CircleHelp, tone: "text-sky-300" },
  pending: { label: "Pendiente", Icon: Hourglass, tone: "text-amber-300" },
};

/** Número y nombre de un desarrollo por su clave: "#12 nombre". */
function useDevLabel() {
  const tree = useFolders((s) => s.tree);
  return (key: string) => {
    const n = tree.devIndex?.[key];
    const sid = key.startsWith("s:") ? key.slice(2) : null;
    const it = (tree.later ?? []).find((x) => x.key === key);
    const special: Record<string, string> = { manager: "Manager", recursos: "Recursos", plugins: "Plugins", ide: "IDE" };
    const name = devName(tree.devNames, key) ?? (sid ? tree.sessions.find((s) => s.id === sid)?.title : null)
      ?? it?.devTitle ?? (sid ? special[sid] : null)
      ?? key.replace(/^p:https:\/\/github\.com\/[^/]+\/([^/]+)\/pull\/(\d+)$/, "$1#$2");
    const num = n !== undefined ? `#${n}` : sid && /^\d+$/.test(sid) ? `#${sid}` : "";
    return { num, name: `${name ?? key}${it?.archived ? " (archivado)" : ""}` };
  };
}

function DevLabel({ k, label, big }: { k: string; label: ReturnType<typeof useDevLabel>; big?: boolean }) {
  const { num, name } = label(k);
  return <div className={cn("flex min-w-0 items-baseline gap-1.5 font-semibold text-foreground", big ? "text-[13px]" : "text-[12px]")}>
    {num && <span className="shrink-0 font-mono text-primary">{num}</span>}<span className="truncate">{name}</span></div>;
}

/** Los campos de un bloqueante (crear y editar): tipo, texto, con quién, artefacto y si bloquea el desarrollo. */
function Fields({ devKey, v, set }: { devKey: string | null; v: Form; set: (f: Form) => void }) {
  const arts = useFolders((s) => (devKey ? s.tree.devArtifacts?.[devKey] : undefined)) ?? [];
  return (
    <div className="space-y-2 text-xs">
      <div className="flex gap-1">
        {(["decision", "pending"] as Kind[]).map((k) => {
          const { label, Icon, tone } = KIND[k];
          return <button key={k} type="button" onClick={() => set({ ...v, kind: k })} aria-pressed={v.kind === k}
            title={k === "decision" ? "Algo que decides tú o conversas con alguien" : "Algo que se espera de alguien (documentos, una respuesta, un acceso)"}
            className={cn("flex flex-1 items-center justify-center gap-1 rounded border px-2 py-1", v.kind === k ? "border-primary bg-accent text-foreground" : "border-border text-muted-foreground hover:text-foreground")}>
            <Icon size={12} className={tone} />{label}</button>;
        })}
      </div>
      <textarea autoFocus value={v.text} onChange={(e) => set({ ...v, text: e.target.value })} rows={2} aria-label="Qué es"
        placeholder={v.kind === "decision" ? "la pregunta, en una línea" : "qué se espera (p. ej. documentos de ejemplo del QAS)"}
        className={cn(field, "resize-y")} />
      <input value={v.who} onChange={(e) => set({ ...v, who: e.target.value })} aria-label="Con quién"
        placeholder={v.kind === "decision" ? "con quién conversarla (opcional)" : "de quién se espera (opcional)"} className={field} />
      {arts.length > 0 && (
        <select value={arts.some((a) => a.url === v.art) ? v.art : ""} onChange={(e) => set({ ...v, art: e.target.value })}
          aria-label="Artefacto del desarrollo" className={field}>
          <option value="">— artefacto del desarrollo (opcional) —</option>
          {arts.map((a) => <option key={a.url} value={a.url}>{a.title ?? a.url}</option>)}
        </select>)}
      <input value={v.art} onChange={(e) => set({ ...v, art: e.target.value })} aria-label="Link del artefacto"
        placeholder="o pega el link de un artefacto (opcional)" className={field} />
      <label className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <input type="checkbox" checked={v.blocks} onChange={(e) => set({ ...v, blocks: e.target.checked })} className="mt-0.5" />
        <span><span className="font-semibold text-foreground">Bloquea el desarrollo</span>: la sesión ya no puede avanzar en nada más. El
          desarrollo pasa a Bloqueado hasta que lo cierres.</span>
      </label>
    </div>);
}

type Form = { kind: Kind; text: string; who: string; art: string; blocks: boolean };
const EMPTY: Form = { kind: "decision", text: "", who: "", art: "", blocks: false };

/** «+ Nuevo bloqueante»: un modal con el desarrollo (el actual por defecto) y los campos. */
function NewDialog({ onClose }: { onClose: () => void }) {
  const dev = useCurrentDev();
  const sessions = useFolders((s) => s.tree.sessions);
  const label = useDevLabel();
  const [key, setKey] = useState<string>(dev?.key ?? "");
  const [v, setV] = useState<Form>(EMPTY);
  const [err, setErr] = useState<string | null>(null);
  const opts = sessions.filter((s) => !["main", "ide", "recursos", "plugins"].includes(s.kind ?? "")).map((s) => `s:${s.id}`);
  if (key && !opts.includes(key)) opts.unshift(key);
  const save = () => {
    if (!key || !v.text.trim()) return;
    setErr(null);
    laterAdd(getWs(), key, v.text.trim(), null, { kind: v.kind, with: v.who.trim() || null, artifact: v.art.trim() || null, blocks: v.blocks })
      .then(onClose).catch((e: any) => setErr(e?.message ?? String(e)));
  };
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-md" onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); }}>
        <DialogHeader><DialogTitle className="text-sm">Nuevo bloqueante</DialogTitle></DialogHeader>
        <select value={key} onChange={(e) => setKey(e.target.value)} aria-label="Desarrollo" className={field}>
          <option value="">— desarrollo —</option>
          {opts.map((k) => { const l = label(k); return <option key={k} value={k}>{l.num} {l.name}</option>; })}
        </select>
        <Fields devKey={key || null} v={v} set={setV} />
        {err && <p role="alert" className="text-[11px] text-destructive">{err}</p>}
        <DialogFooter className="gap-2">
          <Button size="sm" variant="ghost" onClick={onClose} title="Cancelar">Cancelar</Button>
          <Button size="sm" disabled={!key || !v.text.trim()} onClick={save} title="Crear (⌘Enter)">Crear</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>);
}

/** Un bloqueante: tipo, texto (click: abre el artefacto, o la sesión si no tiene), con quién y si bloquea. */
function Item({ it, showDev, label }: { it: LaterItem; showDev: boolean; label: ReturnType<typeof useDevLabel> }) {
  const [answer, setAnswer] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [editing, setEditing] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const focus = useLaterFocus((s) => s.id);
  const box = useRef<HTMLDivElement>(null);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (focus !== it.id) return;
    box.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlash(true);
    const t = window.setTimeout(() => { setFlash(false); useLaterFocus.getState().set(null); }, 2000);
    return () => window.clearTimeout(t);
  }, [focus, it.id]);
  const toSession = it.key.startsWith("s:");
  const live = toSession && !it.archived;
  const kind: Kind = it.kind === "pending" ? "pending" : "decision";
  const { Icon, tone, label: kindLabel } = KIND[kind];
  const err = (e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`);
  const send = () => {
    if (!answer?.trim()) return;
    setBusy(true); setMsg(null);
    laterAnswer(getWs(), it.id, answer.trim()).catch((e) => { err(e); setBusy(false); });
  };
  const open = () => {
    if (it.artifact) openExternal(it.artifact);
    else if (live) useFolders.getState().setActive(it.key.slice(2));
    else setMore(!more);
  };
  const saveEdit = () => {
    if (!editing?.text.trim()) return;
    laterUpdate(getWs(), it.id, { text: editing.text.trim(), with: editing.who.trim(), artifact: editing.art.trim(), kind: editing.kind, blocks: editing.blocks })
      .then(() => setEditing(null)).catch(err);
  };
  return (
    <div ref={box} className={cn("mx-2 mb-1.5 rounded-md border bg-card p-2 transition-shadow", it.blocks ? "border-red-400/60" : "border-border",
      flash && "ring-2 ring-primary")}>
      {showDev && <DevLabel k={it.key} label={label} />}
      <div className="mb-0.5 flex flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
        <span className={cn("flex items-center gap-0.5 font-semibold", tone)}><Icon size={11} />{kindLabel}</span>
        {it.blocks && <span className="rounded border border-red-400/70 px-1 font-semibold text-red-300">bloquea</span>}
        {it.with && <span className="max-w-[12rem] truncate rounded border border-border px-1 text-foreground">con {it.with}</span>}
        <span className="shrink-0">· hace {ago(it.created)}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1">
        <button title="Editar" aria-label="Editar"
          onClick={() => setEditing(editing ? null : { kind, text: it.text, who: it.with ?? "", art: it.artifact ?? "", blocks: !!it.blocks })}
          className="rounded p-0.5 hover:bg-accent hover:text-foreground"><Pencil size={11} /></button>
        <button title="Resuelto: cerrarlo sin mandarle nada a la sesión" aria-label="Resuelto"
          onClick={() => laterResolve(getWs(), it.id).catch(err)} className="rounded p-0.5 hover:bg-accent hover:text-emerald-400"><Check size={12} /></button>
        <button title="Descartar" aria-label="Descartar"
          onClick={() => laterDismiss(getWs(), it.id).catch(err)} className="rounded p-0.5 hover:bg-accent hover:text-foreground"><X size={12} /></button>
        </span>
      </div>
      {editing ? (
        <div className="mt-1">
          <Fields devKey={it.key} v={editing} set={setEditing} />
          <div className="mt-1.5 flex gap-1">
            <Button size="sm" className="h-6 px-2 text-[11px]" disabled={!editing.text.trim()} onClick={saveEdit} title="Guardar">Guardar</Button>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setEditing(null)} title="Cancelar">Cancelar</Button>
          </div>
        </div>
      ) : (<>
        <button onClick={open} title={it.artifact ? "Abrir el análisis (artefacto) en el navegador" : live ? "Ir a la sesión" : "Ver el contexto (su sesión está archivada)"}
          className="block w-full text-left text-[12px] font-semibold leading-snug hover:text-primary">
          {it.text}{it.artifact && <ExternalLink size={11} className="ml-1 inline align-[-1px] text-muted-foreground" />}</button>
        {it.context && (more
          ? <p className="mt-0.5 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{it.context}</p>
          : <button onClick={() => setMore(true)} title="Ver el contexto que dejó la sesión"
              className="mt-0.5 text-[10px] text-muted-foreground hover:text-foreground">contexto…</button>)}
        {answer === null ? (
          <button title={live ? "Responder: la respuesta se le manda a la sesión" : "Anotar la respuesta (su sesión está archivada: no le llega)"}
            onClick={() => setAnswer("")} className="mt-1 block text-[11px] text-primary hover:underline">Responder</button>
        ) : (
          <div className="mt-1.5">
            <textarea autoFocus value={answer} onChange={(e) => setAnswer(e.target.value)} rows={3}
              placeholder={kind === "decision" ? "qué se decidió" : "qué llegó o cómo se resolvió"} aria-label="Respuesta"
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); if (e.key === "Escape") setAnswer(null); }}
              className={cn(field, "resize-y")} />
            <div className="mt-1 flex items-center gap-1">
              <Button size="sm" className="h-6 gap-1 px-2 text-[11px]" disabled={busy || !answer.trim()} onClick={send}
                title={live ? "Mandar la respuesta a la sesión (⌘Enter)" : "Guardar la respuesta (⌘Enter)"}>
                <Send size={11} />{live ? "Mandar a la sesión" : "Guardar"}</Button>
              <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" title="Cancelar" onClick={() => setAnswer(null)}>Cancelar</Button>
            </div>
          </div>)}
      </>)}
      {msg && <p role="alert" className="mt-1 text-[11px] text-destructive">{msg}</p>}
    </div>);
}

export function LaterPanel() {
  const dev = useCurrentDev();
  const items = useFolders((s) => s.tree.later) ?? [];
  const label = useDevLabel();
  const [by, setBy] = useState<"dev" | "who">("dev");
  const [creating, setCreating] = useState(false);
  const mineKeys = dev ? devKeys(dev.key, dev.prs) : [];
  const groupOf = (it: LaterItem) => by === "dev" ? it.key : (it.with ?? "");
  const groups = new Map<string, LaterItem[]>();
  for (const it of items) groups.set(groupOf(it), [...(groups.get(groupOf(it)) ?? []), it]);
  const order = [...groups.keys()].sort((a, b) => by === "dev"
    ? Number(mineKeys.includes(b)) - Number(mineKeys.includes(a))
    : (a === "" ? 1 : b === "" ? -1 : groups.get(b)!.length - groups.get(a)!.length));
  const here = items.filter((it) => mineKeys.includes(it.key)).length;
  return (
    <div className="flex h-full flex-col overflow-auto pb-3 text-xs">
      <div className="mx-2.5 mt-2.5 truncate">
        <span className="font-mono text-sm font-bold text-red-400">{items.length}</span>
        <span className="text-muted-foreground"> {items.length === 1 ? "bloqueante" : "bloqueantes"}{dev && items.length > 0 ? ` · ${here} de este desarrollo` : ""}</span>
      </div>
      <div className="mx-2.5 mt-1.5 flex items-center gap-1">
        {(["dev", "who"] as const).map((k) => (
          <button key={k} onClick={() => setBy(k)} title={k === "dev" ? "Agrupar por desarrollo" : "Agrupar por con quién"}
            className={cn("whitespace-nowrap rounded px-1.5 py-0.5 text-[11px]", by === k ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
            {k === "dev" ? "desarrollo" : "con quién"}</button>))}
        <span className="flex-1" />
        <button onClick={() => setCreating(true)} title="Nuevo bloqueante: una decisión o un pendiente de un desarrollo" aria-label="Nuevo bloqueante"
          className="grid h-6 w-6 shrink-0 place-items-center rounded border border-border text-foreground hover:bg-accent">
          <Plus size={13} /></button>
      </div>
      {creating && <NewDialog onClose={() => setCreating(false)} />}
      {!items.length && <p className="mx-2.5 mt-3 text-[11px] text-muted-foreground">
        Nada te frena. Las sesiones dejan acá sus decisiones y lo que esperan de otros (`ide later add`).</p>}
      {order.map((g) => (
        <div key={g || "-"} className="mt-3">
          <div className="mx-2.5 mb-1">
            {by === "dev" ? <DevLabel k={g} label={label} big />
              : <div className="text-[13px] font-semibold text-foreground">{g ? `con ${g}` : "falta definir con quién"}</div>}
          </div>
          {groups.get(g)!.map((it) => <Item key={it.id} it={it} showDev={by === "who"} label={label} />)}
        </div>))}
    </div>);
}
