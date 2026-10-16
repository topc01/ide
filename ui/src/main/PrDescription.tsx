// ui/src/main/PrDescription.tsx
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchPrBody, savePrBody } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

const TASK_RE = /^(\s*(?:[-*+]|\d+[.)])\s+)\[( |x|X)\]/gm;

/** Descripción de la PR: renderizada o en crudo; en crudo se edita directo y "Guardar" (habilitado
 *  si hay cambios) la sube a GitHub (`gh pr edit`). Renderizado muestra el borrador si hay
 *  cambios y sus casillas se marcan con click (también quedan como cambio). */
export function PrDescription({ url }: { url: string }) {
  const [body, setBody] = useState<string | null>(null);
  const [view, setView] = useState<"rendered" | "raw">("rendered");
  const [draft, setDraft] = useState<string | null>(null);      // null = sin cambios
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = useCallback(() => {
    setError(null);
    fetchPrBody(getWs(), url).then((r) => setBody(r.body)).catch((e: any) => setError(e?.message ?? String(e)));
  }, [url]);
  useEffect(() => { setBody(null); setDraft(null); load(); }, [load]);

  const text = draft ?? body ?? "";
  const dirty = draft !== null && draft !== body;
  const save = () => {
    if (!dirty) return;
    setSaving(true); setError(null);
    savePrBody(getWs(), url, draft).then(() => { setBody(draft); setDraft(null); })
      .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setSaving(false));
  };
  // casillas de tareas: la n-ésima del render es el n-ésimo "- [ ]" del markdown
  const toggleTask = (n: number) => {
    let i = 0;
    setDraft(text.replace(TASK_RE, (m, pre: string, mark: string) =>
      i++ === n ? `${pre}[${mark === " " ? "x" : " "}]` : m));
  };
  let task = 0;
  const tab = (v: "rendered" | "raw", label: string, tip: string) => (
    <button title={tip} onClick={() => setView(v)}
      className={cn("rounded-sm px-2 py-0.5 text-xs outline-none", view === v ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
      {label}</button>);

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center gap-1 border-b border-border pb-1">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Descripción</span>
        {dirty && <span className="ml-2 text-[10px] text-primary">cambios sin guardar</span>}
        <span className="flex-1" />
        <Button size="sm" variant={dirty ? "default" : "ghost"} className="mr-2 h-6 px-2 text-xs" disabled={!dirty || saving} onClick={save}
          title="Guardar la descripción en GitHub (gh pr edit); se habilita si hay cambios">
          {saving ? "Guardando…" : "Guardar"}</Button>
        <div className="flex rounded-md border border-border p-0.5">
          {tab("rendered", "Renderizado", "Ver la descripción renderizada")}
          {tab("raw", "Crudo", "Ver y editar el markdown de la descripción")}
        </div>
      </div>
      {error && <p role="alert" className="mb-2 text-xs text-destructive">{error}</p>}
      {body === null && !error && <p className="text-xs text-muted-foreground">cargando…</p>}
      {body !== null && (view === "raw" ? (
        <textarea value={text} onChange={(e) => setDraft(e.target.value)} spellCheck={false} disabled={saving}
          placeholder="Sin descripción."
          className="min-h-40 w-full resize-y rounded-md border border-border bg-muted p-3 font-mono text-xs text-foreground outline-none [field-sizing:content] focus:border-primary" />
      ) : text.trim() === "" ? <p className="text-xs text-muted-foreground">Sin descripción.</p>
        : <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}
            components={{
              a: ({ node: _n, ...p }) => <a {...p} target="_blank" rel="noreferrer" />,
              input: ({ node: _n, ...p }) => {
                if (p.type !== "checkbox") return <input {...p} />;
                const n = task++;
                return <input type="checkbox" checked={!!p.checked} disabled={saving} className="cursor-pointer"
                  title="Marcar/desmarcar (queda como cambio; usa Guardar)" onChange={() => toggleTask(n)} />;
              } }}>{text}</ReactMarkdown></div>)}
    </div>
  );
}
