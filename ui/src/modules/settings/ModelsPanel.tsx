import { useEffect, useState } from "react";
import { useModels } from "../../state/models";
import { fetchModels, downloadModel, deleteModel, subscribeModels } from "../../transport/modelsChannel";
import { getWs } from "../../transport/wsClient";
import { Badge } from "../../components/ui/badge";

const pct = (d: number, t: number) => (t > 0 ? Math.min(100, Math.round((d / t) * 100)) : 0);
const gb = (bytes: number) => (bytes / 1e9).toFixed(1);

function RepoIdInput() {
  const [v, setV] = useState("");
  return (
    <div className="flex gap-1">
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder="mlx-community/..."
        className="flex-1 rounded border border-border bg-transparent px-2 py-1 text-xs" />
      <button onClick={() => { const r = v.trim(); if (r) { downloadModel(getWs(), r); setV(""); } }}
        className="rounded bg-primary px-2 py-1 text-[10px] text-primary-foreground">Descargar</button>
    </div>
  );
}

export function ModelsPanel() {
  const { curated, installed, inUse, downloads, setCatalog, applyEvent } = useModels();
  useEffect(() => {
    const reload = () => fetchModels(getWs()).then(setCatalog).catch(() => {});
    reload();
    return subscribeModels(getWs(), (e) => { applyEvent(e); if (e.kind === "done") reload(); });
  }, [setCatalog, applyEvent]);
  const installedIds = new Set(installed.map((m) => m.repoId));
  const reload = () => fetchModels(getWs()).then(setCatalog).catch(() => {});
  return (
    <div className="flex flex-col gap-4">
      <section>
        <div className="mb-1 text-xs font-medium text-foreground">Catálogo</div>
        <div className="flex flex-col gap-1">
          {curated.map((m) => {
            const dl = downloads[m.repoId];
            const done = installedIds.has(m.repoId) || dl?.done;
            return (
              <div key={m.repoId} data-curated className="rounded border border-border px-2 py-1.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span>{m.label}<span className="text-muted-foreground"> · {m.params} · {m.quant} · {m.sizeGb} GB</span></span>
                  {done ? (
                    <span className="text-[10px] text-muted-foreground">instalado</span>
                  ) : (
                    <button data-download={m.repoId} disabled={!!dl && !dl.error}
                      onClick={() => downloadModel(getWs(), m.repoId)}
                      className="rounded bg-primary px-2 py-0.5 text-[10px] text-primary-foreground disabled:opacity-50">
                      {dl && !dl.error ? `${pct(dl.downloaded, dl.total)}%` : "Descargar"}
                    </button>
                  )}
                </div>
                {dl && !dl.done && !dl.error && (
                  <div className="mt-1 flex items-center gap-2">
                    <div className="h-1 w-full rounded bg-secondary">
                      <div className="h-1 rounded bg-primary" style={{ width: `${pct(dl.downloaded, dl.total)}%` }} />
                    </div>
                    <span className="whitespace-nowrap text-[10px] text-muted-foreground">{gb(dl.downloaded)}/{gb(dl.total)} GB</span>
                  </div>
                )}
                {dl?.error && <div className="mt-1 text-[10px] text-destructive">{dl.error}</div>}
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-1 text-xs font-medium text-foreground">Descargar por repo_id</div>
        <RepoIdInput />
      </section>

      {(() => {
        const known = new Set([...curated.map((m) => m.repoId), ...installed.map((m) => m.repoId)]);
        const extra = Object.entries(downloads).filter(([repoId, d]) => !known.has(repoId) && !d.done);
        if (extra.length === 0) return null;
        return (
          <section>
            <div className="mb-1 text-xs font-medium text-foreground">Descargas</div>
            <div className="flex flex-col gap-1">
              {extra.map(([repoId, d]) => (
                <div key={repoId} data-extra-download className="rounded border border-border px-2 py-1.5 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span>{repoId}</span>
                    {!d.error && <span className="text-[10px] text-muted-foreground">{pct(d.downloaded, d.total)}%</span>}
                  </div>
                  {!d.error && (
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1 w-full rounded bg-secondary">
                        <div className="h-1 rounded bg-primary" style={{ width: `${pct(d.downloaded, d.total)}%` }} />
                      </div>
                      <span className="whitespace-nowrap text-[10px] text-muted-foreground">{gb(d.downloaded)}/{gb(d.total)} GB</span>
                    </div>
                  )}
                  {d.error && <div className="mt-1 text-[10px] text-destructive">{d.error}</div>}
                </div>
              ))}
            </div>
          </section>
        );
      })()}

      <section>
        <div className="mb-1 text-xs font-medium text-foreground">Instalados</div>
        {installed.length === 0 ? (
          <div className="text-xs text-muted-foreground">Ninguno.</div>
        ) : (
          <div className="flex flex-col gap-1">
            {installed.map((m) => (
              <div key={m.repoId} data-installed className="flex items-center justify-between rounded border border-border px-2 py-1.5 text-xs">
                <span>{m.repoId}<span className="text-muted-foreground"> · {gb(m.sizeOnDisk)} GB</span></span>
                <div className="flex items-center gap-2">
                  {m.repoId === inUse && <Badge variant="secondary" className="bg-role-pill text-primary text-[10px]">en uso</Badge>}
                  <button data-delete={m.repoId} onClick={() => deleteModel(getWs(), m.repoId).then(reload)}
                    className="text-[10px] text-muted-foreground hover:text-destructive">Borrar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
