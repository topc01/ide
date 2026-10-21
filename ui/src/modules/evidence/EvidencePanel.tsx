// ui/src/modules/evidence/EvidencePanel.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Camera, Copy, CopyPlus as Dup, Github, Pencil, Plus, Trash2, X } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import {
  evidenceDelete, evidenceDuplicate, evidenceGithub, evidenceList, evidenceMarkdown, evidenceNew, evidenceSave, evidenceShot,
  type EvidenceRun, type EvidenceStep, type GhPr,
} from "../../transport/folderSessions";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { repoShort } from "../sessions/DevCard";
import { cn } from "../../lib/utils";

const field = "w-full rounded border border-border bg-background px-1.5 py-0.5 text-[11px] text-foreground outline-none focus:border-primary";
const iconBtn = "rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40";

const toB64 = (f: File) => new Promise<string>((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(",", 2)[1] ?? "");
  r.onerror = () => bad(r.error);
  r.readAsDataURL(f);
});

/** Módulo Evidencias: los pasos de prueba de la sesión (qué hacer y dónde sacar captura). El paso
 *  actual es el primero sin hacer: una captura pegada (click en el módulo y ⌘V), arrastrada o subida
 *  se le adjunta, lo marca y avanza. Varias corridas (PR, Ticket: "Duplicar"); se edita, se copia en
 *  markdown y se sube como comentario a una PR (`gh pr comment --attach`). */
export function EvidencePanel() {
  const dev = useCurrentDev();
  const tree = useFolders((s) => s.tree);       // se recarga cuando el server avisa cambios
  const sid = dev?.session?.id;
  const [runs, setRuns] = useState<EvidenceRun[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState<null | { kind: "new" | "dup"; label: string }>(null);
  const [publish, setPublish] = useState(false);
  const fileFor = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const fail = (e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`);

  useEffect(() => {
    if (!sid) return;
    evidenceList(getWs(), sid).then((r) => setRuns(r.runs)).catch(fail);
  }, [sid, tree]);
  const run = runs.find((r) => r.id === active) ?? runs[runs.length - 1] ?? null;
  const current = run?.steps.find((s) => !s.done) ?? null;

  const save = (r: EvidenceRun) => {
    setRuns((all) => all.map((x) => (x.id === r.id ? r : x)));
    if (sid) evidenceSave(getWs(), sid, r).catch(fail);
  };
  const attach = useCallback(async (files: File[], stepId?: string | null) => {
    const target = stepId ?? current?.id;
    if (!sid || !run || !target) { setMsg("No hay un paso pendiente al que adjuntar la captura."); return; }
    setBusy(true); setMsg(null);
    try {
      for (const f of files.filter((f) => f.type.startsWith("image/") || f.type.startsWith("video/"))) {
        const r = await evidenceShot(getWs(), sid, run.id, target, f.name || "captura.png", await toB64(f));
        setRuns((all) => all.map((x) => (x.id === r.run.id ? r.run : x)));
      }
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [sid, run, current]);

  if (!dev) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo.</p>;
  if (!sid) return <p className="p-3 text-xs text-muted-foreground">Las evidencias son de un desarrollo con sesión.</p>;

  const createRun = () => {
    if (!ask) return;
    const label = ask.label.trim() || (ask.kind === "dup" ? "Ticket" : "PR");
    const p = ask.kind === "dup" && run ? evidenceDuplicate(getWs(), sid, run.id, label) : evidenceNew(getWs(), sid, label, []);
    p.then((r) => { setRuns((all) => [...all, r.run]); setActive(r.run.id); setAsk(null); if (ask.kind === "new") setEditing(true); }).catch(fail);
  };
  const copy = () => run && evidenceMarkdown(getWs(), sid, run.id)
    .then((r) => navigator.clipboard.writeText(r.markdown)).then(() => setMsg("Copiado (texto; las imágenes las arrastras desde Adjuntos)")).catch(fail);

  return (
    <div tabIndex={0} className="flex h-full flex-col overflow-auto pb-3 text-xs outline-none"
      onPaste={(e) => { const fs = [...e.clipboardData.files]; if (fs.length && !editing) { e.preventDefault(); attach(fs); } }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); attach([...e.dataTransfer.files]); }}>
      <input ref={fileInput} type="file" accept="image/*,video/*" multiple hidden
        onChange={(e) => { attach([...(e.target.files ?? [])], fileFor.current); e.target.value = ""; }} />
      {/* corridas: PR, Ticket, … */}
      <div className="mx-2.5 mt-2.5 flex flex-wrap items-center gap-1">
        {runs.map((r) => (
          <button key={r.id} onClick={() => setActive(r.id)} title={`Corrida "${r.label}"`}
            className={cn("rounded border px-1.5 py-0.5 text-[11px]", r.id === run?.id ? "border-primary text-foreground" : "border-border text-muted-foreground hover:text-foreground")}>
            {r.label} <span className="text-muted-foreground">{r.steps.filter((s) => s.done).length}/{r.steps.length}</span></button>))}
        <button title="Corrida nueva (vacía)" onClick={() => setAsk({ kind: "new", label: "PR" })} className={iconBtn}><Plus size={13} /></button>
        <span className="flex-1" />
        {run && <>
          <button title="Duplicar: mismos pasos, sin capturas (p.ej. para el ticket)" onClick={() => setAsk({ kind: "dup", label: "Ticket" })} className={iconBtn}><Dup size={13} /></button>
          <button title={editing ? "Terminar de editar" : "Editar los pasos"} onClick={() => setEditing(!editing)}
            className={cn(iconBtn, editing && "text-primary")}><Pencil size={13} /></button>
        </>}
      </div>
      {ask && (
        <div className="mx-2.5 mt-1.5 flex gap-1">
          <input autoFocus value={ask.label} onChange={(e) => setAsk({ ...ask, label: e.target.value })} maxLength={60} aria-label="Nombre de la corrida"
            onKeyDown={(e) => { if (e.key === "Enter") createRun(); if (e.key === "Escape") setAsk(null); }} className={field} />
          <Button size="sm" className="h-6 px-2 text-[11px]" title={ask.kind === "dup" ? "Duplicar" : "Crear"} onClick={createRun}>{ask.kind === "dup" ? "Duplicar" : "Crear"}</Button>
        </div>)}
      {!runs.length && !ask && <p className="mx-2.5 mt-3 text-[11px] text-muted-foreground">
        Sin evidencias. La sesión define los pasos con <code>ide evidencias set</code>, o crea una corrida con + y agrégalos.</p>}

      {run && (<>
        {!editing && current && <p className="mx-2.5 mt-2 text-[10px] text-muted-foreground">
          Paso actual: <span className="text-primary">{run.steps.indexOf(current) + 1}</span>. Click acá y ⌘V, o arrastra la captura.</p>}
        {!editing && !current && run.steps.length > 0 && <p className="mx-2.5 mt-2 text-[11px] text-emerald-400">✓ Todos los pasos hechos.</p>}
        <ol className="mt-1.5">
          {run.steps.map((st, i) => editing
            ? <EditStep key={st.id} st={st} i={i} n={run.steps.length}
                onChange={(next) => save({ ...run, steps: next ? run.steps.map((x) => (x.id === st.id ? next : x)) : run.steps.filter((x) => x.id !== st.id) })}
                onMove={(d) => { const s2 = [...run.steps]; [s2[i], s2[i + d]] = [s2[i + d], s2[i]]; save({ ...run, steps: s2 }); }} />
            : <Step key={st.id} sid={sid} st={st} i={i} current={st.id === current?.id} busy={busy}
                onToggle={() => save({ ...run, steps: run.steps.map((x) => (x.id === st.id ? { ...x, done: !x.done } : x)) })}
                onRemoveShot={(name) => save({ ...run, steps: run.steps.map((x) => (x.id === st.id ? { ...x, shots: x.shots.filter((n) => n !== name) } : x)) })}
                onUpload={() => { fileFor.current = st.id; fileInput.current?.click(); }} />)}
        </ol>
        {editing && <div className="mx-2.5 mt-1 flex gap-1">
          <Button size="sm" variant="secondary" className="h-6 gap-1 px-2 text-[11px]" title="Agregar un paso al final"
            onClick={() => save({ ...run, steps: [...run.steps, { id: Math.random().toString(16).slice(2, 10), title: "Paso nuevo", detail: "", shot: true, shots: [], done: false }] })}>
            <Plus size={11} />Paso</Button>
          <span className="flex-1" />
          <Button size="sm" variant="ghost" className="h-6 gap-1 px-2 text-[11px] text-destructive" title="Borrar esta corrida (las capturas quedan en Adjuntos)"
            onClick={() => evidenceDelete(getWs(), sid, run.id).then(() => { setRuns((a) => a.filter((x) => x.id !== run.id)); setActive(null); setEditing(false); }).catch(fail)}>
            <Trash2 size={11} />Borrar corrida</Button>
        </div>}
        {!editing && run.steps.length > 0 && <div className="mx-2.5 mt-2 flex flex-wrap gap-1">
          <Button size="sm" variant="secondary" className="h-6 gap-1 px-2 text-[11px]" title="Copiar los pasos en markdown (para Notion; las imágenes, desde Adjuntos)" onClick={copy}>
            <Copy size={11} />Copiar</Button>
          <Button size="sm" variant="secondary" className="h-6 gap-1 px-2 text-[11px]" disabled={!dev.prs.length}
            title={dev.prs.length ? "Comentario en una PR con los pasos y las capturas (gh pr comment --attach)" : "El desarrollo no tiene PRs abiertas"}
            onClick={() => setPublish(true)}><Github size={11} />Subir a GitHub</Button>
        </div>}
      </>)}
      {msg && <p role={msg.startsWith("⚠") ? "alert" : undefined} className={cn("mx-2.5 mt-1.5 text-[11px]", msg.startsWith("⚠") ? "text-destructive" : "text-muted-foreground")}>{msg}</p>}
      {publish && run && <PublishDialog sid={sid} run={run} prs={dev.prs} onClose={(ok) => { setPublish(false); if (ok) setMsg("Publicado en GitHub"); }} />}
    </div>);
}

function Step({ sid, st, i, current, busy, onToggle, onRemoveShot, onUpload }:
  { sid: string; st: EvidenceStep; i: number; current: boolean; busy: boolean; onToggle: () => void; onRemoveShot: (n: string) => void; onUpload: () => void }) {
  return (
    <li className={cn("mx-2 mb-1.5 rounded-md border p-2", current ? "border-primary bg-primary/5" : "border-border bg-card", st.done && !current && "opacity-80")}>
      <div className="flex items-start gap-1.5">
        <input type="checkbox" checked={st.done} onChange={onToggle} className="mt-0.5 accent-primary" title={st.done ? "Desmarcar" : "Marcar hecho"} aria-label={`Paso ${i + 1} hecho`} />
        <span className={cn("font-mono text-[11px] font-bold", current ? "text-primary" : "text-muted-foreground")}>{i + 1}</span>
        <div className="min-w-0 flex-1">
          <p className={cn("break-words text-[12px] leading-snug", st.done && "text-muted-foreground line-through decoration-muted-foreground/40")}>{st.title}</p>
          {st.detail && <p className="whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{st.detail}</p>}
        </div>
        {st.shot && <Camera size={11} className="mt-0.5 shrink-0 text-muted-foreground" aria-label="lleva captura" />}
        <button title="Subir captura(s) a este paso" aria-label={`Subir captura al paso ${i + 1}`} disabled={busy} onClick={onUpload} className={iconBtn}><Plus size={12} /></button>
      </div>
      {st.shots.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1 pl-6">
        {st.shots.map((n) => {
          const src = `/api/sessions/${encodeURIComponent(sid)}/attachments/${encodeURIComponent(n)}`;
          return (
            <span key={n} className="group/shot relative">
              <a href={src} target="_blank" rel="noreferrer" title={`${n} (abrir)`}>
                <img src={src} alt={`Paso ${i + 1}`} className="h-14 w-20 rounded border border-border object-cover" /></a>
              <button title="Quitar la captura de este paso (el archivo queda en Adjuntos)" aria-label="Quitar captura" onClick={() => onRemoveShot(n)}
                className="absolute -right-1 -top-1 hidden rounded-full bg-card p-0.5 ring-1 ring-border group-hover/shot:block"><X size={10} /></button>
            </span>);
        })}
      </div>}
    </li>);
}

function EditStep({ st, i, n, onChange, onMove }: { st: EvidenceStep; i: number; n: number; onChange: (s: EvidenceStep | null) => void; onMove: (d: number) => void }) {
  const [title, setTitle] = useState(st.title);
  const [detail, setDetail] = useState(st.detail);
  return (
    <li className="mx-2 mb-1.5 rounded-md border border-border bg-card p-2">
      <div className="flex items-center gap-1">
        <span className="font-mono text-[11px] font-bold text-muted-foreground">{i + 1}</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} onBlur={() => title !== st.title && onChange({ ...st, title })} aria-label="Qué hacer" className={field} />
        <button title="Subir" disabled={i === 0} onClick={() => onMove(-1)} className={iconBtn}><ArrowUp size={12} /></button>
        <button title="Bajar" disabled={i === n - 1} onClick={() => onMove(1)} className={iconBtn}><ArrowDown size={12} /></button>
        <button title="Borrar el paso" onClick={() => onChange(null)} className={iconBtn}><X size={12} /></button>
      </div>
      <textarea value={detail} onChange={(e) => setDetail(e.target.value)} onBlur={() => detail !== st.detail && onChange({ ...st, detail })}
        rows={2} placeholder="detalle (opcional)" aria-label="Detalle" className={cn(field, "mt-1 resize-y")} />
      <label className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground" title="Marca el paso como uno donde va captura">
        <input type="checkbox" checked={st.shot} onChange={(e) => onChange({ ...st, shot: e.target.checked })} className="accent-primary" />lleva captura</label>
    </li>);
}

/** Subir a GitHub: elegir la PR y confirmar (es público para el equipo). */
function PublishDialog({ sid, run, prs, onClose }: { sid: string; run: EvidenceRun; prs: GhPr[]; onClose: (ok: boolean) => void }) {
  const [url, setUrl] = useState(prs[prs.length - 1]?.url ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const shots = run.steps.reduce((n, s) => n + s.shots.length, 0);
  const go = () => {
    setBusy(true); setErr(null);
    evidenceGithub(getWs(), sid, run.id, url).then(() => onClose(true)).catch((e: any) => setErr(e?.message ?? String(e))).finally(() => setBusy(false));
  };
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(false); }}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle className="text-sm">¿Comentar las evidencias "{run.label}" en GitHub?</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">{run.steps.length} pasos y {shots} captura{shots === 1 ? "" : "s"} (se suben con gh).</p>
        <div className="space-y-1">
          {prs.map((p) => (
            <label key={p.url} className="flex cursor-pointer items-center gap-2 text-xs" title={p.title}>
              <input type="radio" name="pr" checked={url === p.url} onChange={() => setUrl(p.url)} className="accent-primary" />
              <span className="font-mono font-bold">{repoShort(p.repo)} #{p.number}</span><span className="truncate text-muted-foreground">{p.title}</span>
            </label>))}
        </div>
        {err && <p role="alert" className="text-xs text-destructive">⚠ {err}</p>}
        <DialogFooter className="gap-2">
          <Button size="sm" variant="ghost" title="No" onClick={() => onClose(false)}>Cancelar</Button>
          <Button size="sm" disabled={busy || !url} title="Sí, comentar en la PR" onClick={go}>{busy ? "Subiendo…" : "Sí, comentar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>);
}
