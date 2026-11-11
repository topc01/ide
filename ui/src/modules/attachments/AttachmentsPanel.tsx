// ui/src/modules/attachments/AttachmentsPanel.tsx
import { useCallback, useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { Check, ChevronRight, Copy, Download, Folder, FolderInput, FolderPlus, Link2, Pencil, Trash2, Upload } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { attachmentTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import { addLinkAttachment, attachFile, attachmentUrl, deleteAttachment, isHtml, listAttachments, mkdirAttachment, openHtmlAttachment,
  moveAttachment, renameAttachment, type Attachment } from "../../transport/folderSessions";
import { usePersistentOpen } from "../../lib/persist";
import { cn } from "../../lib/utils";
import { openExternal } from "../../lib/openExternal";

const size = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
export const shortName = (n: string) => (n.split("/").pop() ?? n).replace(/^\d{8}-\d{6}-/, "").replace(/\.url$/i, "");
const URL_RE = /^https?:\/\/\S+$/i;
const DRAG = "application/x-ide-attachment";     // arrastrar un adjunto (para moverlo), no un archivo del computador
const parentOf = (p: string) => p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";

type Sort = "created" | "at" | "name";
const SORTS: Record<Sort, string> = { created: "creación", at: "modificación", name: "nombre" };
const SORT_KEY = "ide.attachments.sort";
const readSort = (): Sort => { try { const v = localStorage.getItem(SORT_KEY); return v === "at" || v === "name" ? v : "created"; } catch { return "created"; } };

/** Módulo Adjuntos: los archivos que compartiste con la sesión del desarrollo (`attachments/`), con
 *  carpetas: abrir, renombrar, mover (arrastrando o con "mover a…"), descargar, copiar la ruta, borrar
 *  y subir más (sobre una carpeta, quedan en ella). Claude los ve en esa misma carpeta. */
export function AttachmentsPanel() {
  const dev = useCurrentDev();
  const tree = useFolders((s) => s.tree);
  const sid = dev?.session?.id;
  const [files, setFiles] = useState<Attachment[]>([]);
  const [dirs, setDirs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSortState] = useState<Sort>(readSort);
  const setSort = (s: Sort) => { setSortState(s); try { localStorage.setItem(SORT_KEY, s); } catch { /* solo memoria */ } };
  const fileRef = useRef<HTMLInputElement>(null);
  const [linking, setLinking] = useState(false);
  const [link, setLink] = useState({ url: "", name: "" });
  const [newDir, setNewDir] = useState<string | null>(null);   // carpeta madre donde se está creando una
  const [dirName, setDirName] = useState("");
  const load = useCallback(() => {
    if (!sid) return;
    listAttachments(getWs(), sid).then((r) => { setFiles(r.files); setDirs(r.dirs ?? []); setError(null); })
      .catch((e: any) => setError(e?.message ?? String(e)));
  }, [sid]);
  useEffect(load, [load, tree]);
  const act = (p: Promise<unknown>) => p.then(load).catch((e: any) => setError(e?.message ?? String(e)));
  const saveLink = (url: string, name = "") => {
    if (!URL_RE.test(url.trim())) { setError("tiene que ser un link http(s)"); return; }
    setLinking(false); setLink({ url: "", name: "" });
    act(addLinkAttachment(getWs(), sid!, url.trim(), name.trim()));
  };
  const upload = (list: FileList, dir = "") => {
    for (const f of Array.from(list)) {
      const r = new FileReader();
      r.onload = () => act(attachFile(getWs(), sid!, f.name, String(r.result).split(",", 2)[1] ?? "", false, dir));
      r.readAsDataURL(f);
    }
  };
  /** Soltar sobre una carpeta (o la raíz, ""): un adjunto se mueve; archivos del computador se suben ahí. */
  const drop = (e: DragEvent, dir: string) => {
    const moving = e.dataTransfer.getData(DRAG);
    if (moving) {
      e.preventDefault(); e.stopPropagation();
      if (parentOf(moving) !== dir) act(moveAttachment(getWs(), sid!, moving, dir));
    } else if (e.dataTransfer.files.length) {
      e.preventDefault(); e.stopPropagation(); upload(e.dataTransfer.files, dir);
    }
  };
  const createDir = () => {
    const name = dirName.trim();
    if (name) act(mkdirAttachment(getWs(), sid!, newDir ? `${newDir}/${name}` : name));
    setNewDir(null); setDirName("");
  };
  if (!dev) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo.</p>;
  if (!sid) return <p className="p-3 text-xs text-muted-foreground">Este desarrollo no tiene sesión: los adjuntos son de una sesión.</p>;
  const order = (a: Attachment, b: Attachment) => sort === "name" ? shortName(a.name).localeCompare(shortName(b.name))
    : (b[sort] ?? b.at).localeCompare(a[sort] ?? a.at);
  const ctx: Ctx = { sid, devKey: dev.key, files, dirs, act, drop, order, sort,
    startDir: (parent) => { setNewDir(parent); setDirName(""); } };
  const dirInput = (parent: string) => newDir === parent && (
    <input autoFocus value={dirName} onChange={(e) => setDirName(e.target.value)} placeholder="nombre de la carpeta"
      aria-label="Nombre de la carpeta" onBlur={createDir}
      onKeyDown={(e) => { if (e.key === "Enter") createDir(); if (e.key === "Escape") { setNewDir(null); setDirName(""); } }}
      className="mx-2.5 mb-1 w-[calc(100%-1.25rem)] rounded border border-primary bg-background px-1.5 py-0.5 text-[11px] outline-none" />);
  return (
    <div className="flex h-full flex-col overflow-auto pb-3 text-xs" tabIndex={-1}
      onPaste={(e) => {                         // pegar una URL = guardarla como link; un archivo = subirlo
        if ((e.target as HTMLElement).tagName === "INPUT") return;
        const t = e.clipboardData.getData("text").trim();
        if (e.clipboardData.files.length) { e.preventDefault(); upload(e.clipboardData.files); }
        else if (URL_RE.test(t)) { e.preventDefault(); saveLink(t); }
      }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files") || e.dataTransfer.types.includes(DRAG)) e.preventDefault(); }}
      onDrop={(e) => drop(e, "")}>
      <div className="mx-2.5 mb-1 mt-2.5 flex items-center text-[10px] uppercase tracking-wide text-muted-foreground">
        Adjuntos
        <button title="Nueva carpeta" onClick={() => ctx.startDir("")}
          className="ml-auto flex items-center gap-1 normal-case hover:text-foreground"><FolderPlus size={11} /> carpeta</button>
        <button title="Guardar un link (también: pegar una URL con ⌘V sobre este módulo)" onClick={() => setLinking(!linking)}
          className="ml-2 flex items-center gap-1 normal-case hover:text-foreground"><Link2 size={11} /> link</button>
        <button title="Subir archivos (sin pegarlos en la conversación); también puedes arrastrarlos aquí o sobre una carpeta"
          onClick={() => fileRef.current?.click()} className="ml-2 flex items-center gap-1 normal-case hover:text-foreground">
          <Upload size={11} /> subir</button>
        <input ref={fileRef} type="file" multiple hidden onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = ""; }} />
      </div>
      <div className="mx-2.5 mb-1 flex items-center gap-1 text-[10px] text-muted-foreground">
        ordenar por
        {(Object.keys(SORTS) as Sort[]).map((k) => (
          <button key={k} title={`Ordenar por fecha de ${SORTS[k]}`.replace("fecha de nombre", "nombre")} onClick={() => setSort(k)}
            className={cn("rounded px-1", sort === k ? "bg-accent text-foreground" : "hover:text-foreground")}>{SORTS[k]}</button>))}
      </div>
      {linking && (
        <div className="mx-2.5 mb-2 space-y-1">
          <input autoFocus value={link.url} onChange={(e) => setLink({ ...link, url: e.target.value })} placeholder="https://…"
            aria-label="URL" onKeyDown={(e) => { if (e.key === "Enter") saveLink(link.url, link.name); if (e.key === "Escape") setLinking(false); }}
            className="w-full rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[11px] outline-none focus:border-primary" />
          <input value={link.name} onChange={(e) => setLink({ ...link, name: e.target.value })} placeholder="nombre (opcional)"
            aria-label="Nombre del link" onKeyDown={(e) => { if (e.key === "Enter") saveLink(link.url, link.name); if (e.key === "Escape") setLinking(false); }}
            className="w-full rounded border border-border bg-background px-1.5 py-0.5 text-[11px] outline-none focus:border-primary" />
        </div>)}
      {error && <p role="alert" className="mx-2.5 text-destructive">{error}</p>}
      {dirInput("")}
      {!files.length && !dirs.length && <p className="mx-2.5 text-[11px] text-muted-foreground">
        Nada todavía. Arrastra o pega archivos en la tab claude (o súbelos aquí): quedan en attachments/ de la sesión.</p>}
      <Level ctx={ctx} dir="" depth={0} dirInput={dirInput} />
    </div>
  );
}

interface Ctx {
  sid: string; devKey: string; files: Attachment[]; dirs: string[]; sort: Sort;
  act: (p: Promise<unknown>) => void; drop: (e: DragEvent, dir: string) => void;
  order: (a: Attachment, b: Attachment) => number; startDir: (parent: string) => void;
}

/** El contenido de una carpeta: primero sus subcarpetas, después sus archivos (en el orden elegido). */
function Level({ ctx, dir, depth, dirInput }: { ctx: Ctx; dir: string; depth: number; dirInput: (parent: string) => ReactNode }) {
  const sub = ctx.dirs.filter((d) => parentOf(d) === dir).sort((a, b) => a.localeCompare(b));
  const here = ctx.files.filter((f) => parentOf(f.name) === dir).sort(ctx.order);
  return (<>
    {sub.map((d) => <FolderRow key={d} ctx={ctx} dir={d} depth={depth} dirInput={dirInput} />)}
    {here.map((f) => <FileRow key={f.name} ctx={ctx} f={f} depth={depth} />)}
  </>);
}

function FolderRow({ ctx, dir, depth, dirInput }: { ctx: Ctx; dir: string; depth: number; dirInput: (parent: string) => ReactNode }) {
  const [open, setOpen] = usePersistentOpen(`att.${ctx.sid}.${dir}`, true);
  const [over, setOver] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirm, setConfirm] = useState(false);
  const count = ctx.files.filter((f) => f.name.startsWith(`${dir}/`)).length;
  const name = dir.split("/").pop() ?? dir;
  return (
    <div onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { setOver(false); ctx.drop(e, dir); }}>
      <div draggable onDragStart={(e) => { e.dataTransfer.setData(DRAG, dir); e.dataTransfer.effectAllowed = "move"; }}
        className={cn("group mx-1.5 flex items-center gap-1 rounded px-1.5 py-1 hover:bg-accent/60", over && "bg-primary/15 ring-1 ring-primary/50")}
        style={{ paddingLeft: 6 + depth * 12 }}>
        {renaming ? (
          <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Nuevo nombre de la carpeta"
            onKeyDown={(e) => {
              if (e.key === "Escape") setRenaming(false);
              if (e.key === "Enter") { setRenaming(false); if (draft.trim() && draft !== name) ctx.act(renameAttachment(getWs(), ctx.sid, dir, draft.trim())); }
            }} onBlur={() => setRenaming(false)}
            className="min-w-0 flex-1 rounded border border-primary bg-background px-1 py-0.5 font-mono text-[11px] outline-none" />
        ) : (
          <button title={open ? `Plegar ${dir}` : `Desplegar ${dir}`} onClick={() => setOpen(!open)}
            className="flex min-w-0 flex-1 items-center gap-1 text-left font-mono text-[11px]">
            <ChevronRight size={11} className={cn("shrink-0 transition-transform", open && "rotate-90")} />
            <Folder size={11} className="shrink-0 text-primary" /><span className="truncate">{name}</span>
            <span className="shrink-0 text-[10px] text-muted-foreground">{count}</span>
          </button>)}
        {confirm ? (<>
          <button title={`Sí, borrar la carpeta y sus ${count} archivos`} onClick={() => { setConfirm(false); ctx.act(deleteAttachment(getWs(), ctx.sid, dir)); }}
            className="rounded border border-destructive/60 px-1 text-[10px] text-destructive">borrar{count ? ` (${count})` : ""}</button>
          <button title="No" onClick={() => setConfirm(false)} className="px-1 text-[10px] text-muted-foreground">no</button>
        </>) : (
          <span className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
            <button title="Nueva carpeta dentro de esta" aria-label="Nueva subcarpeta" onClick={() => { setOpen(true); ctx.startDir(dir); }}
              className="rounded p-1 text-muted-foreground hover:text-foreground"><FolderPlus size={11} /></button>
            <MoveTo ctx={ctx} name={dir} />
            <button title="Renombrar la carpeta" aria-label="Renombrar" onClick={() => { setRenaming(true); setDraft(name); }}
              className="rounded p-1 text-muted-foreground hover:text-foreground"><Pencil size={11} /></button>
            <button title={count ? `Borrar la carpeta y sus ${count} archivos` : "Borrar la carpeta"} aria-label="Borrar" onClick={() => setConfirm(true)}
              className="rounded p-1 text-muted-foreground hover:text-destructive"><Trash2 size={11} /></button>
          </span>)}
      </div>
      {open && (<>
        {dirInput(dir)}
        <Level ctx={ctx} dir={dir} depth={depth + 1} dirInput={dirInput} />
      </>)}
    </div>
  );
}

function FileRow({ ctx, f, depth }: { ctx: Ctx; f: Attachment; depth: number }) {
  const open = useDevTabs((s) => s.open);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [copied, setCopied] = useState(false);
  const base = f.name.split("/").pop() ?? f.name;
  const when = (ctx.sort === "created" ? f.created ?? f.at : f.at).replace("T", " ");
  return (
    <div draggable onDragStart={(e) => { e.dataTransfer.setData(DRAG, f.name); e.dataTransfer.effectAllowed = "move"; }}
      className="group mx-1.5 flex items-center gap-1.5 rounded px-1.5 py-1 hover:bg-accent/60" style={{ paddingLeft: 6 + depth * 12 + (depth ? 12 : 0) }}>
      {renaming ? (
        <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Nuevo nombre"
          onKeyDown={(e) => {
            if (e.key === "Escape") setRenaming(false);
            if (e.key === "Enter") { setRenaming(false); if (draft.trim() && draft !== base) ctx.act(renameAttachment(getWs(), ctx.sid, f.name, draft.trim())); }
          }}
          onBlur={() => setRenaming(false)}
          className="min-w-0 flex-1 rounded border border-primary bg-background px-1 py-0.5 font-mono text-[11px] outline-none" />
      ) : (
        <button title={f.url ? `Abrir ${f.url}` : isHtml(f.name) ? `Abrir ${f.name} en el navegador (como página)` : `Abrir ${f.name}`}
          onClick={() => f.url ? openExternal(f.url)
            : isHtml(f.name) ? openHtmlAttachment(ctx.sid, f.name) : open(ctx.devKey, attachmentTab(ctx.sid, f.name))}
          className="min-w-0 flex-1 text-left">
          <span className="flex items-center gap-1 truncate font-mono text-[11px]">
            {f.url && <Link2 size={11} className="shrink-0 text-primary" />}{shortName(f.name)}</span>
          <span className="block truncate text-[10px] text-muted-foreground">
            {f.url ? f.url.replace(/^https?:\/\//, "") : `${size(f.size)} · ${when}`}</span>
        </button>)}
      {confirm ? (<>
        <button title="Sí, borrar" onClick={() => { setConfirm(false); ctx.act(deleteAttachment(getWs(), ctx.sid, f.name)); }}
          className="rounded border border-destructive/60 px-1 text-[10px] text-destructive">borrar</button>
        <button title="No" onClick={() => setConfirm(false)} className="px-1 text-[10px] text-muted-foreground">no</button>
      </>) : (
        <span className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
          <button title={f.url ? "Copiar el link" : "Copiar la ruta (para mencionarlo en la conversación)"} aria-label="Copiar"
            onClick={() => navigator.clipboard.writeText(f.url ?? f.path).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); })}
            className="rounded p-1 text-muted-foreground hover:text-foreground">
            {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}</button>
          <MoveTo ctx={ctx} name={f.name} />
          <button title="Renombrar" aria-label="Renombrar" onClick={() => { setRenaming(true); setDraft(f.url ? shortName(base) : base); }}
            className="rounded p-1 text-muted-foreground hover:text-foreground"><Pencil size={11} /></button>
          {!f.url && <a title="Descargar" aria-label="Descargar" href={attachmentUrl(ctx.sid, f.name, true)}
            className="rounded p-1 text-muted-foreground hover:text-foreground"><Download size={11} /></a>}
          <button title="Borrar" aria-label="Borrar" onClick={() => setConfirm(true)}
            className="rounded p-1 text-muted-foreground hover:text-destructive"><Trash2 size={11} /></button>
        </span>)}
    </div>
  );
}

/** "Mover a…": la raíz o cualquier carpeta (menos la actual y, si es una carpeta, ella misma y las suyas). */
function MoveTo({ ctx, name }: { ctx: Ctx; name: string }) {
  const [open, setOpen] = useState(false);
  const here = parentOf(name);
  const targets = ["", ...ctx.dirs].filter((d) => d !== here && d !== name && !d.startsWith(`${name}/`));
  if (!targets.length) return null;
  return (
    <span className="relative">
      <button title="Mover a otra carpeta (también: arrastrarlo)" aria-label="Mover a…" onClick={() => setOpen(!open)}
        className="rounded p-1 text-muted-foreground hover:text-foreground"><FolderInput size={11} /></button>
      {open && (
        <span className="absolute right-0 top-full z-20 mt-1 block max-h-60 w-48 overflow-auto rounded-md border border-border bg-popover p-1 shadow"
          onMouseLeave={() => setOpen(false)}>
          {targets.map((d) => (
            <button key={d || "~raiz"} title={d ? `Mover a ${d}` : "Mover a la raíz de Adjuntos"}
              onClick={() => { setOpen(false); ctx.act(moveAttachment(getWs(), ctx.sid, name, d)); }}
              className="block w-full truncate rounded px-2 py-1 text-left font-mono text-[11px] hover:bg-accent">{d || "(raíz)"}</button>))}
        </span>)}
    </span>
  );
}
