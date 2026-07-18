import { useEffect, useRef, useState } from "react";
import { fetchPage, savePage, type BlockNoteDoc } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";
import { NotionEditor } from "./NotionEditor";

type Status = "idle" | "saving" | "saved" | "error";

export function NotionPageTab({ id }: { id: string }) {
  const pageId = id.slice("notion:".length);
  const [title, setTitle] = useState("");
  const [loaded, setLoaded] = useState<BlockNoteDoc | null>(null);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [structural, setStructural] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncKey, setSyncKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    fetchPage(getWs(), pageId)
      .then((d) => { if (!cancelled) { setTitle(d.title); setLoaded(d.blocks); setUnsupported(d.unsupportedIds); setSyncKey((k) => k + 1); } })
      .catch((e) => { if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado"); });
    return () => { cancelled = true; };
  }, [pageId]);

  function onChange(edited: BlockNoteDoc) {
    if (!loaded) return;
    clearTimeout(timer.current);
    setStatus("saving");
    timer.current = setTimeout(async () => {
      try {
        const res = await savePage(getWs(), pageId, loaded, edited, unsupported);
        setStructural(res.structural);
        if (res.failed.length) { setStatus("error"); }
        else { setStatus("saved"); if (!res.structural) setLoaded(edited); }
        if (res.structural) {
          const d = await fetchPage(getWs(), pageId);      // re-sync tras estructural
          setLoaded(d.blocks); setUnsupported(d.unsupportedIds); setSyncKey((k) => k + 1);
        }
      } catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
    }, 800);
  }

  if (error) return <div className="p-4 text-sm text-destructive">no se pudo abrir la página — {error}</div>;
  if (!loaded) return <div className="p-4 text-sm text-muted-foreground">cargando…</div>;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <span className="text-lg font-bold text-foreground">{title}</span>
        <span className="text-[10px] text-muted-foreground">
          {status === "saving" ? "guardando…" : status === "saved" ? "guardado" : status === "error" ? "error al guardar" : ""}
        </span>
      </div>
      {structural && (
        <div className="border-b border-border bg-[#2e2820] px-5 py-2 text-[11px] text-[#e0863f]">
          Los cambios de estructura (agregar/quitar bloques) llegan en Fase 2; se guardaron solo las ediciones de texto.
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <NotionEditor key={syncKey} initial={loaded} onChange={onChange} />
      </div>
    </div>
  );
}
