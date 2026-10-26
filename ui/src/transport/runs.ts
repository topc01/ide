// ui/src/transport/runs.ts
import { useEffect, useState } from "react";
import type { WsClient } from "./ws";
import { getWs } from "./wsClient";

/** Un script corriendo (o que corrió) en un worktree. `place` = id de la sesión o `wt-<repo>-<n>`. */
export interface Run {
  place: string; repo: string; name: string;
  state: "running" | "stopping" | "stopped" | "exited" | "lost";
  exitCode: number | null; pid: number | null; started: string | null; ended: string | null; urls: string[];
  error?: string | null;        // `[ide] error: <motivo>` del script (p.ej. puerto tomado en el host)
  branch?: string | null;       // la rama que se levantó (o @sha si el worktree estaba en detach)
}
/** Worktree de una PR sin sesión. */
export interface PrPlace { id: string; repos: string[]; heads?: Record<string, string | null> }
export interface RunsState { runs: Run[]; places: PrPlace[] }
type Target = { place: string; repo: string; name: string };

export const fetchRuns = (ws: WsClient): Promise<RunsState> => ws.request("runs.list", {});
/** `apiPort`: un front (embed/admin) apunta a esa api antes de levantar (su `run` llama a point-api). */
export const startRun = (ws: WsClient, t: Target & { apiPort?: number | null }): Promise<Run> => ws.request("runs.start", t);
export const stopRun = (ws: WsClient, t: Target): Promise<Run> => ws.request("runs.stop", t);
export const runLog = (ws: WsClient, t: Target, offset: number): Promise<{ data: string; end: number; reset: boolean }> =>
  ws.request("runs.log", { ...t, offset });
export const ensurePrWorktree = (ws: WsClient, url: string): Promise<{ place: string; repo: string; created: boolean }> =>
  ws.request("prwt.ensure", { url });
export const updatePrWorktree = (ws: WsClient, url: string): Promise<{ head: string }> =>
  ws.request("prwt.update", { url });
export const removePrWorktree = (ws: WsClient, place: string, force = false): Promise<{ ok: boolean }> =>
  ws.request("prwt.remove", { place, force });

export interface FileEntry { name: string; type: "dir" | "file"; size: number | null }
export const listWtFiles = (ws: WsClient, place: string, repo: string, path: string): Promise<{ entries: FileEntry[] }> =>
  ws.request("wtfiles.list", { place, repo, path });
export const envFiles = (ws: WsClient, place: string, repo: string): Promise<{ files: string[] }> =>
  ws.request("wtfiles.envs", { place, repo });
export const readWtFile = (ws: WsClient, place: string, repo: string, path: string): Promise<{ text: string; mtime: string }> =>
  ws.request("wtfiles.read", { place, repo, path });
export const statWtFile = (ws: WsClient, place: string, repo: string, path: string): Promise<{ mtime: string | null }> =>
  ws.request("wtfiles.stat", { place, repo, path });
export const writeWtFile = (ws: WsClient, place: string, repo: string, path: string, text: string,
                            mtime: string | null): Promise<{ mtime: string }> =>
  ws.request("wtfiles.write", { place, repo, path, text, mtime });

/** Bases de los worktrees de un lugar (las que su `.env` nombra) y abrir su visor (pgweb). */
export const listDbs = (ws: WsClient, place: string): Promise<{ dbs: { repo: string; name: string; running: boolean }[] }> =>
  ws.request("db.list", { place });
export const openDb = (ws: WsClient, place: string, repo: string): Promise<{ url: string; name: string }> =>
  ws.request("db.open", { place, repo });

/** Estado de los servidores, vivo (`runs.changed`). */
export function useRuns(): { state: RunsState | null; error: string | null } {
  const [state, setState] = useState<RunsState | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const ws = getWs();
    fetchRuns(ws).then(setState).catch((e: any) => setError(e?.message ?? String(e)));
    const h = (p: RunsState) => { setState(p); setError(null); };
    ws.on("runs.changed", h);
    return () => ws.off("runs.changed", h);
  }, []);
  return { state, error };
}

/** `wt-<repo>-<n>`: el worktree de una PR sin sesión (mismo slug que el server). */
export const prPlace = (repo: string, number: number) =>
  `wt-${repo}-${number}`.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");
