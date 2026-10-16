// ui/src/modules/servers/ServersPanel.tsx
import { useState } from "react";
import { ExternalLink, Play, Square } from "lucide-react";
import { useFolders } from "../../state/folders";
import { runTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import {
  ensurePrWorktree, removePrWorktree, startRun, stopRun, updatePrWorktree, type Run,
} from "../../transport/runs";
import { Button } from "../../components/ui/button";
import { repoShort } from "../sessions/DevCard";
import { cn } from "../../lib/utils";
import { useDevPlace } from "./place";

const HIDDEN = new Set(["archive"]);            // corre solo al archivar / quitar el worktree
const STATE: Record<Run["state"], [string, string]> = {
  running: ["corriendo", "bg-emerald-400"], stopping: ["parando…", "bg-amber-300"],
  stopped: ["parado", "bg-muted-foreground/50"], exited: ["terminó", "bg-muted-foreground/50"],
  lost: ["murió", "bg-destructive"],
};
const alive = (r?: Run) => r?.state === "running" || r?.state === "stopping";

export function RunState({ run }: { run?: Run }) {
  if (!run) return <span className="h-1.5 w-1.5 shrink-0 rounded-full border border-muted-foreground/40" title="no se ha corrido" />;
  const [label, tone] = STATE[run.state];
  const bad = run.state === "exited" && run.exitCode !== 0;
  return <span title={run.state === "exited" ? `terminó (exit ${run.exitCode})` : label}
    className={cn("h-1.5 w-1.5 shrink-0 rounded-full", bad ? "bg-destructive" : tone, run.state === "running" && "animate-pulse")} />;
}

export function RunUrls({ run }: { run?: Run }) {
  if (!run || !alive(run) || !run.urls.length) return null;
  return <>{run.urls.map((u) => (
    <a key={u} href={u} target="_blank" rel="noreferrer" title={`Abrir ${u}`} onClick={(e) => e.stopPropagation()}
      className="inline-flex items-center gap-0.5 font-mono text-[10px] text-primary hover:underline">
      :{u.split(":").pop()}<ExternalLink size={9} /></a>))}</>;
}

/** Módulo Servidores: los scripts de cada repo del desarrollo actual, corriendo aparte del IDE. */
export function ServersPanel() {
  const { dev, runs, error, place } = useDevPlace();
  const scripts = useFolders((s) => s.tree.scripts);
  const open = useDevTabs((s) => s.open);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmRm, setConfirmRm] = useState(false);
  const act = (what: string, p: Promise<unknown>) => {
    setBusy(what); setErr(null);
    p.catch((e: any) => setErr(e?.message ?? String(e))).finally(() => setBusy(null));
  };
  if (!dev || !place) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo para ver sus servidores.</p>;
  const runOf = (repo: string, name: string) =>
    runs?.runs.find((r) => r.place === place.place && r.repo === repo && r.name === name);
  const openLog = (repo: string, name: string) =>
    open(dev.key, runTab(place.place, repo, name, `${repoShort(repo)} ${name}`));
  const others = (runs?.runs ?? []).filter((r) => alive(r) && r.place !== place.place);

  return (
    <div className="flex h-full flex-col overflow-auto py-2 text-xs">
      {err && <p role="alert" className="mx-2.5 mb-2 text-destructive">{err}</p>}
      {error && <p role="alert" className="mx-2.5 mb-2 text-destructive">desconectado: {error}</p>}
      {!place.exists && place.pr && (
        <div className="mx-2.5 rounded-md border border-dashed border-border p-2.5">
          <p className="text-muted-foreground">Esta PR no tiene sesión. Para levantarla, el IDE crea un worktree en el head de
            la PR (en detach: no ocupa la rama); después corre lo que necesites (install, build, run).</p>
          <Button size="sm" className="mt-2" disabled={busy !== null}
            title={`Crear .ide/worktrees/${place.place}/${place.pr.repo} en el head de la PR`}
            onClick={() => act("ensure", ensurePrWorktree(getWs(), place.pr!.url).then((r) => {
              if (r.created && (scripts[r.repo] ?? []).some((s) => s.name === "setup")) openLog(r.repo, "setup");
            }))}>
            {busy === "ensure" ? "Preparando…" : `Preparar ${repoShort(place.pr.repo)} #${place.pr.number}`}</Button>
        </div>)}
      {place.exists && place.repos.length === 0 && <p className="mx-2.5 text-muted-foreground">La sesión no tiene repos.</p>}
      {place.exists && place.repos.map((repo) => {
        const list = (scripts[repo] ?? []).filter((s) => !HIDDEN.has(s.name));
        return (
          <div key={repo} className="mb-3">
            <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">{repo}</div>
            {list.length === 0 && <p className="px-2.5 text-muted-foreground">Sin scripts en <span className="font-mono">.ide/scripts/{repo}/</span></p>}
            {list.map((s) => {
              const run = runOf(repo, s.name);
              const key = `${repo}/${s.name}`;
              return (
                <div key={s.name} role="button" tabIndex={0} title={run ? `Ver el log de ${s.name}` : `${s.name}: todavía no se corrió`}
                  onClick={() => run && openLog(repo, s.name)}
                  className={cn("group flex items-center gap-2 px-2.5 py-1", run && "cursor-pointer hover:bg-accent/60")}>
                  <RunState run={run} />
                  <span className="font-mono">{s.name}</span>
                  {!s.executable && <span className="text-destructive" title={`chmod +x .ide/scripts/${repo}/${s.name}`}>⚠ no ejecutable</span>}
                  <span className="flex min-w-0 flex-1 flex-wrap gap-1.5"><RunUrls run={run} /></span>
                  {alive(run) ? (
                    <button aria-label={`Parar ${s.name}`} title={`Parar ${s.name} (SIGTERM al grupo; SIGKILL a los 15 s)`}
                      disabled={run!.state === "stopping" || busy === key}
                      onClick={(e) => { e.stopPropagation(); act(key, stopRun(getWs(), { place: place.place, repo, name: s.name })); }}
                      className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40">
                      <Square size={12} /></button>
                  ) : (
                    <button aria-label={`Correr ${s.name}`} title={`Correr ${s.name} en el worktree de ${repo} (sigue aunque cierres el IDE)`}
                      disabled={!s.executable || busy === key}
                      onClick={(e) => {
                        e.stopPropagation();
                        act(key, startRun(getWs(), { place: place.place, repo, name: s.name }).then(() => openLog(repo, s.name)));
                      }}
                      className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-primary disabled:opacity-40">
                      <Play size={12} /></button>)}
                </div>);
            })}
          </div>);
      })}
      {place.exists && place.pr && (
        <div className="mx-2.5 mb-3 flex flex-wrap gap-1.5">
          <Button size="sm" variant="secondary" disabled={busy !== null} title="Mover el worktree al último commit de la PR (si no tiene cambios)"
            onClick={() => act("update", updatePrWorktree(getWs(), place.pr!.url))}>
            {busy === "update" ? "Actualizando…" : "Actualizar al head"}</Button>
          {confirmRm ? (<>
            <Button size="sm" variant="destructive" disabled={busy !== null}
              title="Parar sus servidores, correr archive y borrar el worktree (se pierden sus cambios y sus .env)"
              onClick={() => { setConfirmRm(false); act("rm", removePrWorktree(getWs(), place.place)); }}>¿Seguro? Quitar</Button>
            <Button size="sm" variant="ghost" title="No quitar" onClick={() => setConfirmRm(false)}>No</Button>
          </>) : (
            <Button size="sm" variant="ghost" disabled={busy !== null} title="Parar sus servidores, correr archive y borrar el worktree de la PR"
              onClick={() => setConfirmRm(true)}>{busy === "rm" ? "Quitando…" : "Quitar worktree"}</Button>)}
        </div>)}
      {others.length > 0 && (
        <div className="mt-auto border-t border-border pt-2">
          <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Corriendo en otros desarrollos</div>
          {others.map((r) => (
            <div key={`${r.place}/${r.repo}/${r.name}`} className="flex items-center gap-2 px-2.5 py-1">
              <RunState run={r} />
              <span className="min-w-0 truncate font-mono" title={`${r.place} · ${r.repo}/${r.name}`}>
                {r.place} <span className="text-muted-foreground">{repoShort(r.repo)}/{r.name}</span></span>
              <span className="flex flex-1 gap-1.5"><RunUrls run={r} /></span>
              <button aria-label={`Parar ${r.name} de ${r.place}`} title={`Parar ${r.repo}/${r.name} de ${r.place}`}
                disabled={r.state === "stopping"}
                onClick={() => act(`o:${r.place}`, stopRun(getWs(), r))}
                className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40">
                <Square size={12} /></button>
            </div>))}
        </div>)}
    </div>
  );
}
