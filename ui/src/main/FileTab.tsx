// ui/src/main/FileTab.tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import CodeMirror, { EditorView, keymap, type Extension } from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { getWs } from "../transport/wsClient";
import { readWtFile, writeWtFile } from "../transport/runs";
import { Button } from "../components/ui/button";

function language(path: string): Extension[] {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (["ts", "tsx", "js", "jsx", "mjs", "cjs"].includes(ext)) return [javascript({ jsx: true, typescript: ext.startsWith("ts") })];
  if (ext === "py") return [python()];
  if (ext === "json") return [json()];
  if (ext === "md") return [markdown()];
  if (ext === "yml" || ext === "yaml") return [yaml()];
  return [];
}

// tema 1a (ámbar/terminal) sobre el oscuro de CodeMirror
const theme = EditorView.theme({
  "&": { backgroundColor: "var(--background)", color: "var(--foreground)", height: "100%", fontSize: "12px" },
  ".cm-content": { fontFamily: '"JetBrains Mono", ui-monospace, monospace', caretColor: "var(--primary)" },
  ".cm-gutters": { backgroundColor: "var(--background)", color: "var(--muted-foreground)", border: "none" },
  ".cm-activeLine, .cm-activeLineGutter": { backgroundColor: "color-mix(in srgb, var(--muted) 70%, transparent)" },
  "&.cm-focused .cm-cursor": { borderLeftColor: "var(--primary)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": { backgroundColor: "color-mix(in srgb, var(--primary) 30%, transparent) !important" },
}, { dark: true });

/** Un archivo del worktree, editable. Guardar: botón o ⌘S; si cambió en disco, avisa en vez de pisar. */
export function FileTab({ place, repo, path }: { place: string; repo: string; path: string }) {
  const [saved, setSaved] = useState<string | null>(null);   // lo que hay en disco
  const [text, setText] = useState<string>("");
  const [mtime, setMtime] = useState<number | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = useCallback(() => {
    setError(null);
    readWtFile(getWs(), place, repo, path)
      .then((r) => { setSaved(r.text); setText(r.text); setMtime(r.mtime); setIsNew(false); })
      .catch((e: any) => {
        if (e?.code === "not_found" || /no existe/.test(e?.message ?? "")) {   // nuevo: se crea al guardar
          setSaved(""); setText(""); setMtime(null); setIsNew(true);
        } else setError(e?.message ?? String(e));
      });
  }, [place, repo, path]);
  useEffect(load, [load]);
  const dirty = saved !== null && (text !== saved || (isNew && text !== ""));
  const save = useCallback(() => {
    if (!dirty || saving) return;
    setSaving(true); setError(null);
    writeWtFile(getWs(), place, repo, path, text, mtime)
      .then((r) => { setSaved(text); setMtime(r.mtime); setIsNew(false); })
      .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setSaving(false));
  }, [dirty, saving, place, repo, path, text, mtime]);
  const extensions = useMemo(() => [
    theme, EditorView.lineWrapping, ...language(path),
    keymap.of([{ key: "Mod-s", preventDefault: true, run: () => { save(); return true; } }]),
  ], [path, save]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1 text-xs">
        <span className="font-mono text-muted-foreground">{repo}/</span><span className="-ml-2 font-mono">{path}</span>
        <span className="text-muted-foreground">{place}</span>
        {isNew && <span className="text-primary">nuevo: se crea al guardar</span>}
        {dirty && !isNew && <span className="text-primary">cambios sin guardar</span>}
        <span className="flex-1" />
        {error && <span role="alert" className="text-destructive" title={error}>⚠ {error}</span>}
        {error && /cambió en disco/.test(error) && (
          <Button size="sm" variant="ghost" className="h-6 px-2" title="Descartar tus cambios y cargar lo que hay en disco" onClick={load}>Recargar</Button>)}
        <Button size="sm" variant={dirty ? "default" : "ghost"} className="h-6 px-2 text-xs" disabled={!dirty || saving}
          title="Guardar en el worktree (⌘S); se habilita si hay cambios" onClick={save}>
          {saving ? "Guardando…" : "Guardar"}</Button>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {saved === null && !error ? <p className="p-4 text-xs text-muted-foreground">cargando…</p> : (
          <CodeMirror value={text} onChange={setText} theme="dark" extensions={extensions} height="100%"
            basicSetup={{ foldGutter: false, highlightActiveLine: true }} className="h-full" />)}
      </div>
    </div>
  );
}
