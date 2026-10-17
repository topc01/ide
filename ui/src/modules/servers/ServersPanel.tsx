// ui/src/modules/servers/ServersPanel.tsx
import { useEffect, useState } from "react";
import { ExternalLink, Play, Square } from "lucide-react";
import { useFolders } from "../../state/folders";
import { dbTab, runTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import {
  ensurePrWorktree, listDbs, openDb, removePrWorktree, startRun, stopRun, updatePrWorktree, type Run,
} from "../../transport/runs";
import { Button } from "../../components/ui/button";
import { repoShort } from "../sessions/DevCard";
import { cn } from "../../lib/utils";
import { useDevPlace } from "./place";

const HIDDEN = new Set(["archive"]);            // corre solo al archivar / quitar el worktree
const alive = (r?: Run) => r?.state === "running" || r?.state === "stopping";

const ago = (iso: string | null) => {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  return s < 60 ? "hace segundos" : s < 3600 ? `hace ${Math.round(s / 60)} min` : s < 86400 ? `hace ${Math.round(s / 3600)} h`
    : `hace ${Math.round(s / 86400)} d`;
};

/** Estado de un script en palabras: corriendo · parando · ✓ terminó · ✗ falló (exit N) · parado · murió. */
export function runState(run?: Run): { text: string; icon: string; cls: string; tip: string } {
  if (!run) return { text: "sin correr", icon: "○", cls: "text-muted-foreground", tip: "todavía no se corrió" };
  const when = `empezó ${ago(run.started)}${run.ended ? ` · terminó ${ago(run.ended)}` : ""}`;
  switch (run.state) {
    case "running": return { text: "corriendo", icon: "●", cls: "text-emerald-400", tip: `sigue corriendo · ${when}` };
    case "stopping": return { text: "parando…", icon: "◌", cls: "text-amber-300", tip: "se le pidió parar (SIGKILL a los 15 s)" };
    case "stopped": return { text: "parado", icon: "■", cls: "text-muted-foreground", tip: `lo paraste · ${when}` };
    case "lost": return { text: "murió", icon: "⚠", cls: "text-destructive",
      tip: "el proceso ya no existe y no dejó código de salida (kill -9, reinicio de la máquina)" };
    default: return run.exitCode === 0
      ? { text: "terminó", icon: "✓", cls: "text-emerald-400", tip: `terminó bien (exit 0) · ${when}` }
      : { text: `falló (exit ${run.exitCode})`, icon: "✗", cls: "text-destructive", tip: `terminó con error (exit ${run.exitCode}) · ${when}` };
  }
}

/** `compact`: solo el ícono (p.ej. en la etiqueta de una tab). */
export function RunState({ run, compact = false }: { run?: Run; compact?: boolean }) {
  const st = runState(run);
  return (
    <span title={st.tip} className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-[10px]", st.cls)}>
      <span className={cn(run?.state === "running" && "animate-pulse")}>{st.icon}</span>{!compact && st.text}
    </span>);
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
                  <span className="w-20 shrink-0 truncate font-mono" title={s.name}>{s.name}</span>
                  <RunState run={run} />
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
      {place.exists && <Databases place={place.place} devKey={dev.key} />}
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
              <RunState run={r} compact />
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

/** Bases de los worktrees del desarrollo (la que nombra su `.env`): abrir su visor (pgweb) en una tab. */
function Databases({ place, devKey }: { place: string; devKey: string }) {
  const open = useDevTabs((s) => s.open);
  const [dbs, setDbs] = useState<{ repo: string; name: string; running: boolean }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { listDbs(getWs(), place).then((r) => setDbs(r.dbs)).catch(() => setDbs([])); }, [place]);
  if (!dbs.length) return null;
  return (
    <div className="mb-3">
      <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Base de datos</div>
      {dbs.map((d) => (
        <div key={d.repo} className="flex items-center gap-2 px-2.5 py-1">
          <span className="w-20 shrink-0 truncate font-mono" title={d.repo}>{d.repo.replace(/^finnecto-/, "")}</span>
          <span className="min-w-0 flex-1 truncate font-mono text-muted-foreground" title={d.name}>{d.name}</span>
          <button disabled={busy !== null} title={`Abrir ${d.name} en pgweb (ver y editar tablas, correr SQL)`}
            onClick={() => {
              setBusy(d.repo); setErr(null);
              openDb(getWs(), place, d.repo).then((r) => open(devKey, dbTab(r.path, r.name)))
                .catch((e: any) => setErr(e?.message ?? String(e))).finally(() => setBusy(null));
            }}
            className="rounded border border-border px-1.5 py-px text-[10px] hover:bg-accent disabled:opacity-40">
            {busy === d.repo ? "abriendo…" : "Abrir"}</button>
        </div>))}
      {err && <p role="alert" className="mx-2.5 text-[11px] text-destructive">{err}</p>}
    </div>
  );
}
