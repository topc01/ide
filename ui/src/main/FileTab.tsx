// ui/src/main/FileTab.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CodeMirror, { EditorView, keymap, type Extension } from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { getWs } from "../transport/wsClient";
import { readWtFile, statWtFile, writeWtFile } from "../transport/runs";
import { Button } from "../components/ui/button";
import { useTheme } from "../state/theme";

function language(path: string): Extension[] {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (["ts", "tsx", "js", "jsx", "mjs", "cjs"].includes(ext)) return [javascript({ jsx: true, typescript: ext.startsWith("ts") })];
  if (ext === "py") return [python()];
  if (ext === "json") return [json()];
  if (ext === "md") return [markdown()];
  if (ext === "yml" || ext === "yaml") return [yaml()];
  return [];
}

// tema 1a (ámbar/terminal) sobre el de CodeMirror (oscuro o claro según el tema del IDE)
const theme = EditorView.theme({
  "&": { backgroundColor: "var(--background)", color: "var(--foreground)", height: "100%", fontSize: "12px" },
  ".cm-content": { fontFamily: '"JetBrains Mono", ui-monospace, monospace', caretColor: "var(--primary)" },
  ".cm-gutters": { backgroundColor: "var(--background)", color: "var(--muted-foreground)", border: "none" },
  ".cm-activeLine, .cm-activeLineGutter": { backgroundColor: "color-mix(in srgb, var(--muted) 70%, transparent)" },
  "&.cm-focused .cm-cursor": { borderLeftColor: "var(--primary)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": { backgroundColor: "color-mix(in srgb, var(--primary) 30%, transparent) !important" },
});

/** Un archivo del worktree, editable. Guardar: botón o ⌘S; si cambió en disco, avisa en vez de pisar. */
export function FileTab({ place, repo, path }: { place: string; repo: string; path: string }) {
  const uiTheme = useTheme((s) => s.theme);
  const [saved, setSaved] = useState<string | null>(null);   // lo que hay en disco
  const [text, setText] = useState<string>("");
  const [mtime, setMtime] = useState<string | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = useCallback(() => {
    setError(null); setConflict(false);
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
  // cambió en disco (p.ej. un script reescribió el .env): sin cambios tuyos se recarga solo; con
  // cambios, se avisa y eliges
  const [conflict, setConflict] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const mtimeRef = useRef(mtime); mtimeRef.current = mtime;
  useEffect(() => {
    let alive = true;
    const t = setInterval(() => {
      if (saved === null || saving) return;
      statWtFile(getWs(), place, repo, path).then((r) => {
        if (!alive || r.mtime === null || r.mtime === mtimeRef.current) return;
        if (!dirtyRef.current) {
          readWtFile(getWs(), place, repo, path).then((f) => {
            if (!alive || dirtyRef.current) { setConflict(true); return; }
            setSaved(f.text); setText(f.text); setMtime(f.mtime); setIsNew(false);
            setNote("se recargó: cambió en disco"); setTimeout(() => alive && setNote(null), 4000);
          }).catch(() => {});
        } else setConflict(true);
      }).catch(() => {});
    }, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [place, repo, path, saved, saving]);
  const write = useCallback((force: boolean) => {
    if (saving) return;
    setSaving(true); setError(null);
    writeWtFile(getWs(), place, repo, path, text, force ? null : mtime)
      .then((r) => { setSaved(text); setMtime(r.mtime); setIsNew(false); setConflict(false); })
      .catch((e: any) => {
        if (/cambió en disco/.test(e?.message ?? "")) setConflict(true); else setError(e?.message ?? String(e));
      }).finally(() => setSaving(false));
  }, [saving, place, repo, path, text, mtime]);
  const save = useCallback(() => { if (dirty) write(false); }, [dirty, write]);
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
        {note && <span className="text-muted-foreground">{note}</span>}
        {error && <span role="alert" className="text-destructive" title={error}>⚠ {error}</span>}
        <Button size="sm" variant={dirty ? "default" : "ghost"} className="h-6 px-2 text-xs" disabled={!dirty || saving}
          title="Guardar en el worktree (⌘S); se habilita si hay cambios" onClick={save}>
          {saving ? "Guardando…" : "Guardar"}</Button>
      </div>
      {conflict && (
        <div role="alert" className="flex flex-wrap items-center gap-2 border-b border-amber-400/40 bg-amber-400/10 px-3 py-1.5 text-xs">
          <span className="text-amber-300">⚠ El archivo cambió en disco mientras lo editabas (p.ej. lo reescribió un script).</span>
          <span className="flex-1" />
          <Button size="sm" variant="ghost" className="h-6 px-2" title="Descartar tus cambios y cargar lo que hay en disco" onClick={load}>
            Recargar (pierdo lo mío)</Button>
          <Button size="sm" className="h-6 px-2" disabled={saving} title="Guardar tu versión encima de la del disco"
            onClick={() => write(true)}>Sobrescribir con lo mío</Button>
        </div>)}
      <div className="min-h-0 flex-1 overflow-hidden">
        {saved === null && !error ? <p className="p-4 text-xs text-muted-foreground">cargando…</p> : (
          <CodeMirror value={text} onChange={setText} theme={uiTheme} extensions={extensions} height="100%"
            basicSetup={{ foldGutter: false, highlightActiveLine: true }} className="h-full" />)}
      </div>
    </div>
  );
}
