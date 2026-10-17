// ui/src/modules/db/DbPanel.tsx
import { useEffect, useState } from "react";
import { dbTab, useDevTabs } from "../../state/devTabs";
import { getWs } from "../../transport/wsClient";
import { listDbs, openDb } from "../../transport/runs";
import { useDevPlace } from "../servers/place";

/** Módulo Base de datos: las bases de los worktrees del desarrollo actual; Abrir = pgweb en una tab. */
export function DbPanel() {
  const { dev, place } = useDevPlace();
  if (!dev || !place) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo para ver sus bases.</p>;
  if (!place.exists) return <p className="p-3 text-xs text-muted-foreground">Esta PR no tiene worktree: prepáralo desde Servidores.</p>;
  return (
    <div className="flex h-full flex-col overflow-auto py-2 text-xs">
      <div className="mx-2.5 mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Base de datos</div>
      <Databases place={place.place} devKey={dev.key} />
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
  if (!dbs.length) return <p className="px-2.5 text-xs text-muted-foreground">Ningún worktree de este desarrollo nombra una base en su .env (POSTGRES_NAME).</p>;
  return (
    <div className="mb-3">
      {dbs.map((d) => (
        <div key={d.repo} className="flex items-center gap-2 px-2.5 py-1">
          <span className="w-20 shrink-0 truncate font-mono" title={d.repo}>{d.repo.replace(/^finnecto-/, "")}</span>
          <span className="min-w-0 flex-1 truncate font-mono text-muted-foreground" title={d.name}>{d.name}</span>
          <button disabled={busy !== null} title={`Abrir ${d.name} en pgweb (ver y editar tablas, correr SQL)`}
            onClick={() => {
              setBusy(d.repo); setErr(null);
              openDb(getWs(), place, d.repo).then((r) => open(devKey, dbTab(r.url, r.name)))
                .catch((e: any) => setErr(e?.message ?? String(e))).finally(() => setBusy(null));
            }}
            className="rounded border border-border px-1.5 py-px text-[10px] hover:bg-accent disabled:opacity-40">
            {busy === d.repo ? "abriendo…" : "Abrir"}</button>
        </div>))}
      {err && <p role="alert" className="mx-2.5 text-[11px] text-destructive">{err}</p>}
    </div>
  );
}
