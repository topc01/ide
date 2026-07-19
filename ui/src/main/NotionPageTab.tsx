import { useEffect, useRef, useState } from "react";
import { fetchPage, savePage, setTitle as setTitleReq, type BlockNoteDoc } from "../transport/notionChannel";
import { getWs } from "../transport/wsClient";
import { NotionEditor } from "./NotionEditor";

type Status = "idle" | "saving" | "saved" | "error";

export function NotionPageTab({ id }: { id: string }) {
  const pageId = id.slice("notion:".length);
  const [title, setTitle] = useState("");
  const [loaded, setLoaded] = useState<BlockNoteDoc | null>(null);
  const [unsupported, setUnsupported] = useState<string[]>([]);
  const [idMap, setIdMap] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [syncKey, setSyncKey] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    fetchPage(getWs(), pageId)
      .then((d) => { if (!cancelled) { setTitle(d.title); setLoaded(d.blocks); setUnsupported(d.unsupportedIds); setIdMap({}); setSyncKey((k) => k + 1); } })
      .catch((e) => { if (!cancelled) setError((e as { message?: string })?.message ?? "desconectado"); });
    return () => { cancelled = true; };
  }, [pageId]);

  function onChange(edited: BlockNoteDoc) {
    if (!loaded) return;
    clearTimeout(timer.current);
    setStatus("saving");
    timer.current = setTimeout(async () => {
      try {
        const res = await savePage(getWs(), pageId, loaded, edited, unsupported, idMap);
        if (res.failed.length) {
          setStatus("error");
          const d = await fetchPage(getWs(), pageId);     // reconciliar a la verdad de Notion
          setLoaded(d.blocks); setUnsupported(d.unsupportedIds); setIdMap({}); setSyncKey((k) => k + 1);
        } else {
          const merged = { ...idMap };
          for (const a of res.appended) merged[a.clientId] = a.notionId;
          setIdMap(merged);
          setLoaded(edited.map((b) => ({ ...b, id: merged[b.id] ?? b.id })));  // rekey a ids de Notion
          setStatus("saved");
        }
      } catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
    }, 800);
  }

  async function commitTitle() {
    try { await setTitleReq(getWs(), pageId, title); }
    catch (e) { setStatus("error"); setError((e as { message?: string })?.message ?? "error"); }
  }

  if (error) return <div className="p-4 text-sm text-destructive">no se pudo abrir la página — {error}</div>;
  if (!loaded) return <div className="p-4 text-sm text-muted-foreground">cargando…</div>;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-border px-5 py-3">
        <input
          className="flex-1 bg-transparent text-lg font-bold text-foreground outline-none"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commitTitle}
        />
        <span className="text-[10px] text-muted-foreground">
          {status === "saving" ? "guardando…" : status === "saved" ? "guardado" : status === "error" ? "error al guardar" : ""}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <NotionEditor key={syncKey} initial={loaded} onChange={onChange} />
      </div>
    </div>
  );
}
