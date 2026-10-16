// ui/src/modules/sessions/RepoLine.tsx
import { useState } from "react";
import { MoreHorizontal } from "lucide-react";
import type { FolderSession, RepoInfo } from "../../transport/folderSessions";
import { rmRepo, runScript } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { useFolders } from "../../state/folders";
import { scriptTab, useDevTabs } from "../../state/devTabs";
import { cn } from "../../lib/utils";

export function RepoLine({ session, repo }: { session: FolderSession; repo: RepoInfo }) {
  const { tree, setActive } = useFolders();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scripts = tree.scripts[repo.name] ?? [];
  const launch = async (name: string) => {
    setOpen(false);
    try {
      const { terminalId } = await runScript(getWs(), session.id, repo.name, name);
      setActive(session.id);
      useDevTabs.getState().open(`s:${session.id}`, scriptTab(terminalId, `${repo.name}:${name}`));   // tab del desarrollo
    } catch (e: any) { setError(e?.message ?? String(e)); }
  };
  return (
    <div onClick={(e) => e.stopPropagation()} className="relative flex items-center gap-1.5 pl-4 pt-0.5 text-[10px] text-muted-foreground">
      <span className={cn(repo.state === "missing" && "text-destructive line-through")}>{repo.name}</span>
      <span className="font-mono text-primary">{repo.branch ?? "(detached)"}</span>
      {repo.state === "missing" && <span className="text-destructive">missing</span>}
      {repo.state === "missing" && (
        <button title="Quitar este repo de la sesión" onClick={() => rmRepo(getWs(), session.id, repo.name).catch((e: any) => setError(e?.message ?? String(e)))}
          className="text-[10px] underline text-muted-foreground hover:text-foreground">quitar</button>)}
      {repo.setup === "ok" && <span className="text-muted-foreground">✓ setup</span>}
      {repo.setup === "failed" && <span className="text-destructive">✗ setup</span>}
      {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
      {repo.state !== "missing" && (
        <button aria-label={`Scripts de ${repo.name}`} title={`Scripts de ${repo.name}`} onClick={() => setOpen((o) => !o)}
          className="ml-auto text-muted-foreground hover:text-foreground"><MoreHorizontal size={12} /></button>)}
      {open && (
        <div role="menu" className="absolute right-2 top-5 z-10 w-44 rounded-md border border-border bg-popover p-1 shadow">
          {scripts.length === 0 && <div className="px-2 py-1 text-muted-foreground">sin scripts en .ide/scripts/{repo.name}/</div>}
          {scripts.map((s) => (
            <button key={s.name} role="menuitem" aria-disabled={!s.executable}
              title={s.executable ? undefined : `chmod +x .ide/scripts/${repo.name}/${s.name}`}
              onClick={() => s.executable && launch(s.name)}
              className={cn("block w-full rounded px-2 py-1 text-left hover:bg-accent",
                !s.executable && "cursor-not-allowed text-muted-foreground")}>
              {s.name}{!s.executable && " ⚠ no ejecutable"}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
