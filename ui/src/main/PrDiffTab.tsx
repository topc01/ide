// ui/src/main/PrDiffTab.tsx
import { useEffect, useRef, useState } from "react";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView, lineNumbers } from "@codemirror/view";
import { MergeView, unifiedMergeView } from "@codemirror/merge";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { yaml } from "@codemirror/lang-yaml";
import { getWs } from "../transport/wsClient";
import { prFileDiff } from "../transport/folderSessions";
import { cn } from "../lib/utils";

function language(path: string): Extension[] {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (["ts", "tsx", "js", "jsx", "mjs", "cjs", "vue"].includes(ext)) return [javascript({ jsx: true, typescript: ext.startsWith("ts") || ext === "vue" })];
  if (ext === "py") return [python()];
  if (ext === "json") return [json()];
  if (ext === "md") return [markdown()];
  if (ext === "yml" || ext === "yaml") return [yaml()];
  return [];
}

const theme = EditorView.theme({
  "&": { backgroundColor: "var(--background)", color: "var(--foreground)", fontSize: "12px" },
  ".cm-content": { fontFamily: '"JetBrains Mono", ui-monospace, monospace' },
  ".cm-gutters": { backgroundColor: "var(--background)", color: "var(--muted-foreground)", border: "none" },
  ".cm-changedLine, .cm-insertedLine": { backgroundColor: "rgba(34,197,94,0.10) !important" },
  ".cm-deletedChunk, .cm-deletedLine": { backgroundColor: "rgba(239,68,68,0.12) !important" },
  ".cm-changedText": { background: "rgba(34,197,94,0.25) !important" },
  ".cm-deletedText": { background: "rgba(239,68,68,0.28) !important" },
  ".cm-mergeView": { height: "100%" },
}, { dark: true });

/** Diff de un archivo de una PR (contra su base): lado a lado o unificado, solo lectura. */
export const PrDiffTab = PrDiffView;
export function PrDiffView({ url, path, oldPath }: { url: string; path: string; oldPath: string | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<"split" | "unified">(() => {
    try { return (localStorage.getItem("ide.diffMode") as "split" | "unified") || "split"; } catch { return "split"; }
  });
  const [data, setData] = useState<{ old: string | null; new: string | null; local: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setData(null); setError(null);
    prFileDiff(getWs(), url, path, oldPath).then(setData).catch((e: any) => setError(e?.message ?? String(e)));
  }, [url, path, oldPath]);
  useEffect(() => {
    if (!data || !ref.current) return;
    const ext = [theme, EditorView.editable.of(false), EditorState.readOnly.of(true), lineNumbers(), ...language(path)];
    const a = data.old ?? "", b = data.new ?? "";
    let destroy: () => void;
    if (mode === "split") {
      const mv = new MergeView({ a: { doc: a, extensions: ext }, b: { doc: b, extensions: ext }, parent: ref.current,
        collapseUnchanged: { margin: 3, minSize: 6 }, gutter: true });
      destroy = () => mv.destroy();
    } else {
      const v = new EditorView({ parent: ref.current, state: EditorState.create({ doc: b,
        extensions: [...ext, unifiedMergeView({ original: a, mergeControls: false, collapseUnchanged: { margin: 3, minSize: 6 } })] }) });
      destroy = () => v.destroy();
    }
    return () => destroy();
  }, [data, mode, path]);
  const pick = (m: "split" | "unified") => { setMode(m); try { localStorage.setItem("ide.diffMode", m); } catch { /* */ } };
  const tab = (m: "split" | "unified", label: string) => (
    <button title={m === "split" ? "Ver lado a lado" : "Ver unificado"} onClick={() => pick(m)}
      className={cn("rounded-sm px-2 py-0.5 text-xs outline-none", mode === m ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>{label}</button>);
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3 py-1 text-xs">
        <span className="font-mono">{oldPath && oldPath !== path ? `${oldPath} → ${path}` : path}</span>
        {data?.old === null && <span className="text-emerald-400">nuevo</span>}
        {data?.new === null && <span className="text-red-400">borrado</span>}
        {data?.local && <span className="text-muted-foreground" title="La rama está en un worktree del IDE: incluye lo no commiteado">worktree local</span>}
        <span className="flex-1" />
        {error && <span role="alert" className="text-destructive">⚠ {error}</span>}
        <div className="flex rounded-md border border-border p-0.5">{tab("split", "Lado a lado")}{tab("unified", "Unificado")}</div>
      </div>
      {!data && !error && <p className="p-4 text-xs text-muted-foreground">cargando…</p>}
      <div ref={ref} className="min-h-0 flex-1 overflow-auto" />
    </div>
  );
}
