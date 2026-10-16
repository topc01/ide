// ui/src/main/PrDescription.tsx
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchPrBody, savePrBody } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

/** Descripción de la PR: renderizada o en crudo, y editable (guardar = `gh pr edit` en GitHub). */
export function PrDescription({ url }: { url: string }) {
  const [body, setBody] = useState<string | null>(null);
  const [view, setView] = useState<"rendered" | "raw">("rendered");
  const [draft, setDraft] = useState<string | null>(null);      // null = no se está editando
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = useCallback(() => {
    setError(null);
    fetchPrBody(getWs(), url).then((r) => setBody(r.body)).catch((e: any) => setError(e?.message ?? String(e)));
  }, [url]);
  useEffect(() => { setBody(null); setDraft(null); load(); }, [load]);

  const save = () => {
    if (draft === null) return;
    setSaving(true); setError(null);
    savePrBody(getWs(), url, draft).then(() => { setBody(draft); setDraft(null); })
      .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setSaving(false));
  };
  const tab = (v: "rendered" | "raw", label: string) => (
    <button title={`Ver la descripción ${label.toLowerCase()}`} onClick={() => setView(v)} disabled={draft !== null}
      className={cn("rounded px-2 py-0.5 text-xs", view === v && draft === null ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
      {label}</button>);

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center gap-1 border-b border-border pb-1">
        <span className="mr-2 text-[10px] uppercase tracking-wide text-muted-foreground">Descripción</span>
        {tab("rendered", "Renderizado")}{tab("raw", "Crudo")}
        <span className="flex-1" />
        {draft === null ? (
          <Button size="sm" variant="ghost" disabled={body === null} title="Editar la descripción (se guarda en GitHub)"
            onClick={() => setDraft(body ?? "")}>Editar</Button>
        ) : (<>
          <Button size="sm" variant="ghost" title="Descartar los cambios" onClick={() => setDraft(null)} disabled={saving}>Cancelar</Button>
          <Button size="sm" title="Guardar la descripción en GitHub (gh pr edit)" onClick={save} disabled={saving || draft === body}>
            {saving ? "Guardando…" : "Guardar en GitHub"}</Button>
        </>)}
      </div>
      {error && <p role="alert" className="mb-2 text-xs text-destructive">{error}</p>}
      {body === null && !error && <p className="text-xs text-muted-foreground">cargando…</p>}
      {draft !== null ? (
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false}
          className="h-[60vh] w-full resize-y rounded-md border border-border bg-background p-3 font-mono text-xs outline-none focus:border-primary" />
      ) : body !== null && (body.trim() === "" ? <p className="text-xs text-muted-foreground">Sin descripción.</p>
        : view === "raw" ? <pre className="whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 font-mono text-xs">{body}</pre>
        : <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}
            components={{ a: ({ node: _n, ...p }) => <a {...p} target="_blank" rel="noreferrer" /> }}>{body}</ReactMarkdown></div>)}
    </div>
  );
}
