// ui/src/modules/attachments/AttachmentsPanel.tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Download, Link2, Pencil, Trash2, Upload } from "lucide-react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { attachmentTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import { addLinkAttachment, attachFile, attachmentUrl, deleteAttachment, listAttachments, renameAttachment, type Attachment } from "../../transport/folderSessions";
import { cn } from "../../lib/utils";

const size = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
export const shortName = (n: string) => n.replace(/^\d{8}-\d{6}-/, "").replace(/\.url$/i, "");
const URL_RE = /^https?:\/\/\S+$/i;

/** Módulo Adjuntos: los archivos que compartiste con la sesión del desarrollo (`attachments/`): abrir,
 *  renombrar, descargar, copiar la ruta, borrar y subir más. Claude los ve en esa misma carpeta. */
export function AttachmentsPanel() {
  const dev = useCurrentDev();
  const tree = useFolders((s) => s.tree);
  const open = useDevTabs((s) => s.open);
  const sid = dev?.session?.id;
  const [files, setFiles] = useState<Attachment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [linking, setLinking] = useState(false);
  const [link, setLink] = useState({ url: "", name: "" });
  const saveLink = (url: string, name = "") => {
    if (!URL_RE.test(url.trim())) { setError("tiene que ser un link http(s)"); return; }
    setLinking(false); setLink({ url: "", name: "" });
    act(addLinkAttachment(getWs(), sid!, url.trim(), name.trim()));
  };
  const load = useCallback(() => {
    if (!sid) return;
    listAttachments(getWs(), sid).then((r) => { setFiles(r.files); setError(null); }).catch((e: any) => setError(e?.message ?? String(e)));
  }, [sid]);
  useEffect(load, [load, tree]);
  const act = (p: Promise<unknown>) => p.then(load).catch((e: any) => setError(e?.message ?? String(e)));
  const upload = (list: FileList) => {
    for (const f of Array.from(list)) {
      const r = new FileReader();
      r.onload = () => act(attachFile(getWs(), sid!, f.name, String(r.result).split(",", 2)[1] ?? "", false));
      r.readAsDataURL(f);
    }
  };
  if (!dev) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo.</p>;
  if (!sid) return <p className="p-3 text-xs text-muted-foreground">Este desarrollo no tiene sesión: los adjuntos son de una sesión.</p>;
  return (
    <div className="flex h-full flex-col overflow-auto pb-3 text-xs" tabIndex={-1}
      onPaste={(e) => {                         // pegar una URL = guardarla como link; un archivo = subirlo
        if ((e.target as HTMLElement).tagName === "INPUT") return;
        const t = e.clipboardData.getData("text").trim();
        if (e.clipboardData.files.length) { e.preventDefault(); upload(e.clipboardData.files); }
        else if (URL_RE.test(t)) { e.preventDefault(); saveLink(t); }
      }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); }}
      onDrop={(e) => { if (e.dataTransfer.files.length) { e.preventDefault(); upload(e.dataTransfer.files); } }}>
      <div className="mx-2.5 mb-1 mt-2.5 flex items-center text-[10px] uppercase tracking-wide text-muted-foreground">
        Adjuntos
        <button title="Guardar un link (también: pegar una URL con ⌘V sobre este módulo)" onClick={() => setLinking(!linking)}
          className="ml-auto flex items-center gap-1 normal-case hover:text-foreground"><Link2 size={11} /> link</button>
        <button title="Subir archivos (sin pegarlos en la conversación); también puedes arrastrarlos aquí"
          onClick={() => fileRef.current?.click()} className="ml-2 flex items-center gap-1 normal-case hover:text-foreground">
          <Upload size={11} /> subir</button>
        <input ref={fileRef} type="file" multiple hidden onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = ""; }} />
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
      {!files.length && <p className="mx-2.5 text-[11px] text-muted-foreground">
        Nada todavía. Arrastra o pega archivos en la tab claude (o súbelos aquí): quedan en attachments/ de la sesión.</p>}
      {files.map((f) => (
        <div key={f.name} className="group mx-1.5 flex items-center gap-1.5 rounded px-1.5 py-1 hover:bg-accent/60">
          {renaming === f.name ? (
            <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Nuevo nombre"
              onKeyDown={(e) => {
                if (e.key === "Escape") setRenaming(null);
                if (e.key === "Enter") { setRenaming(null); if (draft.trim() && draft !== f.name) act(renameAttachment(getWs(), sid, f.name, draft.trim())); }
              }}
              onBlur={() => setRenaming(null)}
              className="min-w-0 flex-1 rounded border border-primary bg-background px-1 py-0.5 font-mono text-[11px] outline-none" />
          ) : (
            <button title={f.url ? `Abrir ${f.url}` : `Abrir ${f.name}`}
              onClick={() => f.url ? window.open(f.url, "_blank", "noopener,noreferrer") : open(dev.key, attachmentTab(sid, f.name))}
              className="min-w-0 flex-1 text-left">
              <span className="flex items-center gap-1 truncate font-mono text-[11px]">
                {f.url && <Link2 size={11} className="shrink-0 text-primary" />}{shortName(f.name)}</span>
              <span className="block truncate text-[10px] text-muted-foreground">
                {f.url ? f.url.replace(/^https?:\/\//, "") : `${size(f.size)} · ${f.at.replace("T", " ")}`}</span>
            </button>)}
          {confirm === f.name ? (<>
            <button title="Sí, borrar" onClick={() => { setConfirm(null); act(deleteAttachment(getWs(), sid, f.name)); }}
              className="rounded border border-destructive/60 px-1 text-[10px] text-destructive">borrar</button>
            <button title="No" onClick={() => setConfirm(null)} className="px-1 text-[10px] text-muted-foreground">no</button>
          </>) : (
            <span className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
              <button title={f.url ? "Copiar el link" : "Copiar la ruta (para mencionarlo en la conversación)"} aria-label="Copiar"
                onClick={() => navigator.clipboard.writeText(f.url ?? f.path).then(() => { setCopied(f.name); setTimeout(() => setCopied(null), 1200); })}
                className="rounded p-1 text-muted-foreground hover:text-foreground">
                {copied === f.name ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}</button>
              <button title="Renombrar" aria-label="Renombrar" onClick={() => { setRenaming(f.name); setDraft(f.url ? shortName(f.name) : f.name); }}
                className="rounded p-1 text-muted-foreground hover:text-foreground"><Pencil size={11} /></button>
              {!f.url && <a title="Descargar" aria-label="Descargar" href={attachmentUrl(sid, f.name, true)}
                className="rounded p-1 text-muted-foreground hover:text-foreground"><Download size={11} /></a>}
              <button title="Borrar" aria-label="Borrar" onClick={() => setConfirm(f.name)}
                className={cn("rounded p-1 text-muted-foreground hover:text-destructive")}><Trash2 size={11} /></button>
            </span>)}
        </div>))}
    </div>
  );
}
