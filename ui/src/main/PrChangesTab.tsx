// ui/src/main/PrChangesTab.tsx
import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { getWs } from "../transport/wsClient";
import { prFiles, type PrFile } from "../transport/folderSessions";
import { PrDiffView } from "./PrDiffTab";
import { cn } from "../lib/utils";

const STATUS: Record<string, [string, string, string]> = {
  A: ["A", "text-emerald-400", "nuevo"], M: ["M", "text-amber-300", "modificado"], D: ["D", "text-red-400", "borrado"],
  R: ["R", "text-sky-300", "renombrado"], "?": ["?", "text-emerald-300", "sin trackear (worktree local)"],
};
const KEY = (url: string) => `ide.changesSel.${url}`;

/** Cambios de una PR contra su base (en un stack, la de abajo): la lista de archivos a la izquierda
 *  (el que estás viendo, destacado) y su diff a la derecha. */
export function PrChangesTab({ url }: { url: string }) {
  const [data, setData] = useState<{ files: PrFile[]; base: string; mergeBase: string; local: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState<string | null>(() => { try { return localStorage.getItem(KEY(url)); } catch { return null; } });
  const load = useCallback((fresh = false) => {
    setLoading(true); setError(null);
    prFiles(getWs(), url, fresh).then((d) => {
      setData(d);
      setSel((cur) => cur && d.files.some((f) => f.path === cur) ? cur : d.files[0]?.path ?? null);
    }).catch((e: any) => setError(e?.message ?? String(e))).finally(() => setLoading(false));
  }, [url]);
  useEffect(() => load(), [load]);
  const pick = (path: string) => { setSel(path); try { localStorage.setItem(KEY(url), path); } catch { /* */ } };
  const file = data?.files.find((f) => f.path === sel) ?? null;
  const total = data?.files.reduce((t, f) => [t[0] + f.additions, t[1] + f.deletions], [0, 0]) ?? [0, 0];
  return (
    <div className="flex h-full min-h-0">
      <div className="flex w-80 shrink-0 flex-col border-r border-border">
        <div className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
          <span title={data ? `contra ${data.base} desde ${data.mergeBase}` : ""}>vs {data?.base ?? "…"}</span>
          {data && <span>{data.files.length} archivos · <span className="text-emerald-400">+{total[0]}</span> <span className="text-red-400">−{total[1]}</span></span>}
          <span className="flex-1" />
          <button title="Volver a traer los cambios desde GitHub" onClick={() => load(true)} className="hover:text-foreground">
            <RefreshCw size={11} className={cn(loading && "animate-spin")} /></button>
        </div>
        {data?.local && <div className="border-b border-border px-3 py-1 text-[10px] text-muted-foreground"
          title={data.local}>incluye lo no commiteado del worktree local</div>}
        {error && <p role="alert" className="p-3 text-xs text-destructive">{error}</p>}
        {!data && !error && <p className="p-3 text-xs text-muted-foreground">trayendo los cambios…</p>}
        <div className="min-h-0 flex-1 overflow-auto py-1">
          {data?.files.map((f) => {
            const [letter, cls, what] = STATUS[f.status] ?? [f.status, "text-muted-foreground", f.status];
            const slash = f.path.lastIndexOf("/");
            const on = f.path === sel;
            return (
              <button key={f.path} onClick={() => pick(f.path)} title={`${what}: ${f.oldPath ? `${f.oldPath} → ` : ""}${f.path}`}
                className={cn("flex w-full items-start gap-2 border-l-2 px-3 py-1.5 text-left hover:bg-accent/60",
                  on ? "border-primary bg-accent" : "border-transparent")}>
                <span className={cn("mt-px w-3 shrink-0 font-mono text-xs font-bold", cls)}>{letter}</span>
                <span className="min-w-0 flex-1">
                  <span className={cn("block truncate font-mono text-xs", on && "font-semibold")}>{f.path.slice(slash + 1)}</span>
                  {slash >= 0 && <span className="block truncate font-mono text-[10px] text-muted-foreground" style={{ direction: "rtl", textAlign: "left" }}>
                    {f.path.slice(0, slash)}</span>}
                </span>
                {(f.additions > 0 || f.deletions > 0) && <span className="shrink-0 font-mono text-[10px]">
                  <span className="text-emerald-400">+{f.additions}</span> <span className="text-red-400">−{f.deletions}</span></span>}
              </button>);
          })}
          {data && !data.files.length && <p className="p-3 text-xs text-muted-foreground">Sin cambios contra {data.base}.</p>}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        {file ? <PrDiffView key={`${url}:${file.path}`} url={url} path={file.path} oldPath={file.oldPath} />
          : <p className="p-4 text-xs text-muted-foreground">{data ? "Elige un archivo." : ""}</p>}
      </div>
    </div>
  );
}
