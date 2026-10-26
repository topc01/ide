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
import { devBlocks, runPort, useDevPlace, type ServerBlock } from "./place";

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
  if (run.error) return { text: "error", icon: "✗", cls: "text-destructive", tip: `${run.error} · ${when}` };
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

/** Módulo Servidores: un bloque por stack de cada repo del desarrollo (y por repo de la sesión sin PR),
 *  con su rama y dónde se levanta: el worktree de la sesión si está en una rama del stack, si no uno
 *  aparte (`wt-<repo>-<n>`, en la PR de más arriba) que se crea al dar ▶. Los fronts (repos con
 *  `point-api`) apuntan a la api elegida en su bloque (por defecto, la de la PR de la que dependen). */
export function ServersPanel() {
  const { dev, runs, error } = useDevPlace();
  const scripts = useFolders((s) => s.tree.scripts);
  const open = useDevTabs((s) => s.open);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmRm, setConfirmRm] = useState<string | null>(null);
  const [apiPick, setApiPick] = useState<Record<string, string>>({});
  const act = (what: string, p: Promise<unknown>) => {
    setBusy(what); setErr(null);
    p.catch((e: any) => setErr(e?.message ?? String(e))).finally(() => setBusy(null));
  };
  if (!dev) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo para ver sus servidores.</p>;
  const blocks = devBlocks(dev, runs);
  const runOf = (b: ServerBlock, name: string) =>
    runs?.runs.find((r) => r.place === b.place && r.repo === b.repo && r.name === name);
  const openLog = (b: ServerBlock, name: string) =>
    open(dev.key, runTab(b.place, b.repo, name, `${repoShort(b.repo)}${b.prs.length ? ` #${b.prs[b.prs.length - 1].number}` : ""} ${name}`));
  const has = (repo: string, name: string) => (scripts[repo] ?? []).some((s) => s.name === name);
  const isFront = (b: ServerBlock) => has(b.repo, "point-api");
  // las apis del desarrollo: bloques de repos con `run` que no son front
  const apis = blocks.filter((b) => !isFront(b) && has(b.repo, "run"));
  const apiLabel = (b: ServerBlock) => {
    const port = runPort(alive(runOf(b, "run")) ? runOf(b, "run") : undefined);
    const prs = b.prs.length ? b.prs.map((p) => `#${p.number}`).join("→") : b.branch ?? "";
    return `${repoShort(b.repo)} ${prs} · ${port ? `:${port}` : "sin correr"}`;
  };
  const defaultApi = (b: ServerBlock): ServerBlock | null => {
    const deps = b.prs.flatMap((p) => (p.deps ?? []).map((d) => d.url));
    const dep = apis.find((a) => a.prs.some((p) => deps.includes(p.url)));
    if (dep) return dep;
    const running = apis.filter((a) => alive(runOf(a, "run")));
    return running.length === 1 ? running[0] : null;
  };
  const apiOf = (b: ServerBlock): ServerBlock | null => {
    const pick = apiPick[b.key];
    if (pick === "env") return null;
    return (pick && apis.find((a) => a.key === pick)) || defaultApi(b);
  };
  const start = (b: ServerBlock, name: string) => {
    const api = isFront(b) && name === "run" ? apiOf(b) : null;
    const apiPort = api ? runPort(runOf(api, "run")) : null;
    const go = async () => {
      if (!b.exists && b.top) await ensurePrWorktree(getWs(), b.top.url);   // worktree aparte, al primer ▶
      await startRun(getWs(), { place: b.place, repo: b.repo, name, apiPort });
      openLog(b, name);
    };
    act(`${b.key}/${name}`, go());
  };
  const placeKeys = new Set(blocks.map((b) => `${b.place}|${b.repo}`));
  const others = (runs?.runs ?? []).filter((r) => alive(r) && !placeKeys.has(`${r.place}|${r.repo}`));

  return (
    <div className="flex h-full flex-col overflow-auto py-2 text-xs">
      {err && <p role="alert" className="mx-2.5 mb-2 text-destructive">{err}</p>}
      {error && <p role="alert" className="mx-2.5 mb-2 text-destructive">desconectado: {error}</p>}
      {blocks.length === 0 && <p className="mx-2.5 text-muted-foreground">El desarrollo no tiene repos ni PRs para levantar.</p>}
      {blocks.map((b) => {
        const list = (scripts[b.repo] ?? []).filter((s) => !HIDDEN.has(s.name));
        const api = isFront(b) ? apiOf(b) : null;
        const apiRunning = api ? alive(runOf(api, "run")) : false;
        return (
          <div key={b.key} className="mx-2 mb-2.5 rounded-md border border-border">
            <div className="border-b border-border px-2 py-1.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[11px] font-bold">{repoShort(b.repo)}</span>
                {b.prs.length ? <span className="font-mono text-[11px]" title={b.prs.map((p) => `#${p.number} ${p.title}`).join("\n")}>
                  {b.prs.map((p) => `#${p.number}`).join(" → ")}</span>
                  : <span className="text-muted-foreground">sin PR</span>}
                <span className={cn("ml-auto rounded px-1 text-[10px]", b.where === "session" ? "bg-primary/15 text-primary"
                  : b.exists ? "bg-sky-500/15 text-sky-300" : "bg-muted text-muted-foreground")}
                  title={b.where === "session" ? "Se levanta en el worktree de la sesión (donde trabaja claude)"
                    : b.exists ? `Worktree aparte: .ide/worktrees/${b.place}/${b.repo} (en el head de la PR de más arriba)`
                    : "Todavía sin worktree: se crea al dar ▶ (aparte, sin tocar el de la sesión)"}>
                  {b.where === "session" ? "sesión" : b.exists ? "aparte" : "se prepara al ▶"}</span>
              </div>
              <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground" title={`rama: ${b.branch ?? "?"}`}>⎇ {b.branch ?? "?"}</div>
              {isFront(b) && (
                <label className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground" title="A qué api apunta su run (point-api)">
                  api:
                  <select value={apiPick[b.key] ?? (api ? api.key : "env")} onChange={(e) => setApiPick({ ...apiPick, [b.key]: e.target.value })}
                    className="min-w-0 flex-1 rounded border border-border bg-background px-1 py-0.5 text-[11px] text-foreground outline-none">
                    <option value="env">la de su .env.local</option>
                    {apis.map((a) => <option key={a.key} value={a.key}>{apiLabel(a)}{defaultApi(b)?.key === a.key ? " (su dependencia)" : ""}</option>)}
                  </select>
                  {api && !apiRunning && <span className="text-amber-300" title="Levanta primero esa api: si no, el run usa su .env.local">⚠</span>}
                </label>)}
            </div>
            {list.length === 0 && <p className="px-2 py-1 text-muted-foreground">Sin scripts en <span className="font-mono">.ide/scripts/{b.repo}/</span></p>}
            {list.map((s) => {
              const run = runOf(b, s.name);
              const key = `${b.key}/${s.name}`;
              return (
                <div key={s.name} role="button" tabIndex={0} title={run ? `Ver el log de ${s.name}` : `${s.name}: todavía no se corrió`}
                  onClick={() => run && openLog(b, s.name)}
                  className={cn("group flex items-center gap-2 px-2 py-1", run && "cursor-pointer hover:bg-accent/60")}>
                  <span className="w-20 shrink-0 truncate font-mono" title={s.name}>{s.name}</span>
                  <RunState run={run} />
                  {!s.executable && <span className="text-destructive" title={`chmod +x .ide/scripts/${b.repo}/${s.name}`}>⚠ no ejecutable</span>}
                  <span className="flex min-w-0 flex-1 flex-wrap gap-1.5">{run?.error
                    ? <span className="truncate text-destructive" title={run.error}>{run.error}</span> : <RunUrls run={run} />}</span>
                  {alive(run) ? (
                    <button aria-label={`Parar ${s.name}`} title={`Parar ${s.name} (SIGTERM al grupo; SIGKILL a los 15 s)`}
                      disabled={run!.state === "stopping" || busy === key}
                      onClick={(e) => { e.stopPropagation(); act(key, stopRun(getWs(), { place: b.place, repo: b.repo, name: s.name })); }}
                      className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40">
                      <Square size={12} /></button>
                  ) : (
                    <button aria-label={`Correr ${s.name}`} disabled={!s.executable || busy === key}
                      title={`Correr ${s.name} en ${b.where === "session" ? "el worktree de la sesión" : "el worktree aparte"} (rama ${b.branch ?? "?"})`
                        + (isFront(b) && s.name === "run" && api ? `, apuntando a ${apiLabel(api)}` : "")}
                      onClick={(e) => { e.stopPropagation(); start(b, s.name); }}
                      className="grid h-6 w-6 place-items-center rounded text-muted-foreground hover:bg-accent hover:text-primary disabled:opacity-40">
                      <Play size={12} /></button>)}
                </div>);
            })}
            {b.where === "pr" && b.exists && b.top && (
              <div className="flex flex-wrap gap-1.5 border-t border-border px-2 py-1">
                <button disabled={busy !== null} title="Mover el worktree aparte al último commit de la PR (si no tiene cambios)"
                  onClick={() => act(`u:${b.key}`, updatePrWorktree(getWs(), b.top!.url))}
                  className="text-[11px] text-muted-foreground hover:text-foreground">{busy === `u:${b.key}` ? "actualizando…" : "actualizar al head"}</button>
                {confirmRm === b.key ? (<>
                  <button disabled={busy !== null} title="Parar sus servidores, correr archive y borrar el worktree aparte"
                    onClick={() => { setConfirmRm(null); act(`r:${b.key}`, removePrWorktree(getWs(), b.place)); }}
                    className="text-[11px] text-destructive hover:underline">¿seguro? quitar</button>
                  <button title="No quitar" onClick={() => setConfirmRm(null)} className="text-[11px] text-muted-foreground hover:text-foreground">no</button>
                </>) : (
                  <button disabled={busy !== null} title="Parar sus servidores, correr archive y borrar el worktree aparte"
                    onClick={() => setConfirmRm(b.key)} className="text-[11px] text-muted-foreground hover:text-foreground">quitar worktree</button>)}
              </div>)}
          </div>);
      })}
      {others.length > 0 && (
        <div className="mt-auto border-t border-border pt-2">
          <div className="px-2.5 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Corriendo en otros desarrollos</div>
          {others.map((r) => (
            <div key={`${r.place}/${r.repo}/${r.name}`} className="flex items-center gap-2 px-2.5 py-1">
              <RunState run={r} compact />
              <span className="min-w-0 flex-1 truncate font-mono" title={`${r.place} · ${r.repo}/${r.name} · rama ${r.branch ?? "?"}`}>
                {repoShort(r.repo)}/{r.name} <span className="text-muted-foreground">⎇ {r.branch ?? r.place}</span></span>
              <span className="flex gap-1.5"><RunUrls run={r} /></span>
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
