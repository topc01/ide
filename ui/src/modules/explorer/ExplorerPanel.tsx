// ui/src/modules/explorer/ExplorerPanel.tsx
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, File as FileIcon, Folder, KeyRound, RefreshCw } from "lucide-react";
import { fileTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import { envFiles, listWtFiles, type FileEntry } from "../../transport/runs";
import { useDevPlace } from "../servers/place";
import { usePersistentOpen } from "../../lib/persist";
import { cn } from "../../lib/utils";

const ENV_SUGGESTED = [".env", ".env.local"];

function Node({ place, repo, entry, path, depth, onOpen, version }: {
  place: string; repo: string; entry: FileEntry; path: string; depth: number;
  onOpen: (path: string) => void; version: number;
}) {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState<FileEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    listWtFiles(getWs(), place, repo, path).then((r) => { setChildren(r.entries); setErr(null); })
      .catch((e: any) => setErr(e?.message ?? String(e)));
  }, [place, repo, path]);
  useEffect(() => { if (open) load(); }, [open, load, version]);
  const isDir = entry.type === "dir";
  return (
    <div>
      <button title={isDir ? `Expandir ${path}` : `Abrir ${path}`} data-file-node={path}
        onClick={() => (isDir ? setOpen(!open) : onOpen(path))}
        style={{ paddingLeft: depth * 12 + 8 }}
        className="flex w-full items-center gap-1 py-0.5 pr-2 text-left text-xs hover:bg-accent/60">
        {isDir ? <ChevronRight size={11} className={cn("shrink-0 transition-transform", open && "rotate-90")} />
          : <span className="w-[11px] shrink-0" />}
        {isDir ? <Folder size={12} className="shrink-0 text-primary/80" /> : <FileIcon size={12} className="shrink-0 text-muted-foreground" />}
        <span className={cn("truncate", entry.name.startsWith(".") && "text-muted-foreground")}>{entry.name}</span>
      </button>
      {err && <p className="text-[11px] text-destructive" style={{ paddingLeft: depth * 12 + 24 }}>{err}</p>}
      {open && children?.map((c) => (
        <Node key={c.name} place={place} repo={repo} entry={c} path={`${path}/${c.name}`} depth={depth + 1}
          onOpen={onOpen} version={version} />))}
    </div>
  );
}

function RepoTree({ place, repo, onOpen }: { place: string; repo: string; onOpen: (repo: string, path: string) => void }) {
  const [open, setOpen] = usePersistentOpen(`explorer.${repo}`, true);
  const [entries, setEntries] = useState<FileEntry[] | null>(null);
  const [envs, setEnvs] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    setErr(null);
    listWtFiles(getWs(), place, repo, "").then((r) => setEntries(r.entries)).catch((e: any) => setErr(e?.message ?? String(e)));
    envFiles(getWs(), place, repo).then((r) => setEnvs(r.files)).catch(() => setEnvs([]));
  }, [place, repo, version]);
  const shortcuts = [...new Set([...envs, ...ENV_SUGGESTED])].sort();
  return (
    <div className="mb-2">
      <div className="group flex items-center">
        <button title="Colapsar / expandir" onClick={() => setOpen(!open)}
          className="flex flex-1 items-center gap-1 px-2.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
          <ChevronRight size={11} className={cn("transition-transform", open && "rotate-90")} />{repo}</button>
        <button aria-label={`Recargar ${repo}`} title="Recargar el árbol" onClick={() => setVersion((v) => v + 1)}
          className="mr-2 rounded p-0.5 text-muted-foreground opacity-0 hover:text-foreground group-hover:opacity-100">
          <RefreshCw size={11} /></button>
      </div>
      {open && (<>
        <div className="mx-2.5 my-1 flex flex-wrap gap-1">
          {shortcuts.map((f) => {
            const missing = !envs.includes(f);
            return (
              <button key={f} onClick={() => onOpen(repo, f)}
                title={missing ? `${f} no existe: ábrelo y al guardar se crea` : `Editar ${f}`}
                className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] hover:bg-accent",
                  missing ? "border-dashed border-border text-muted-foreground" : "border-primary/40 text-primary")}>
                <KeyRound size={10} />{f}</button>);
          })}
        </div>
        {err && <p className="px-2.5 text-[11px] text-destructive">{err}</p>}
        {entries?.map((e) => (
          <Node key={e.name} place={place} repo={repo} entry={e} path={e.name} depth={0}
            onOpen={(p) => onOpen(repo, p)} version={version} />))}
      </>)}
    </div>
  );
}

/** Módulo Archivos: los worktrees del desarrollo actual, con acceso directo a los `.env*`. */
export function ExplorerPanel() {
  const { dev, place } = useDevPlace();
  const open = useDevTabs((s) => s.open);
  if (!dev || !place) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo para ver sus archivos.</p>;
  if (!place.exists) return <p className="p-3 text-xs text-muted-foreground">Esta PR no tiene sesión ni worktree: prepáralo desde Servidores.</p>;
  if (!place.repos.length) return <p className="p-3 text-xs text-muted-foreground">La sesión no tiene repos.</p>;
  return (
    <div className="h-full overflow-auto py-2">
      {place.repos.map((repo) => (
        <RepoTree key={`${place.place}/${repo}`} place={place.place} repo={repo}
          onOpen={(r, p) => open(dev.key, fileTab(place.place, r, p))} />))}
    </div>
  );
}
