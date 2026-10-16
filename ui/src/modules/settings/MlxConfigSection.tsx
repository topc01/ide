import { useEffect } from "react";
import { useMlxConfig } from "../../state/mlxConfig";
import { useModels } from "../../state/models";
import { getMlxConfig, setMlxConfig, fetchModels } from "../../transport/modelsChannel";
import { getWs } from "../../transport/wsClient";

export function MlxConfigSection() {
  const { enabled, model, routerPrompt, defaultPrompt, error, setConfig, update, setError } = useMlxConfig();
  const installed = useModels((s) => s.installed);
  const setCatalog = useModels((s) => s.setCatalog);
  useEffect(() => { getMlxConfig(getWs()).then(setConfig).catch(() => {}); }, [setConfig]);
  const save = () => {
    setError(null);
    setMlxConfig(getWs(), { enabled, model, routerPrompt })
      .then(() => fetchModels(getWs()).then(setCatalog).catch(() => {}))
      .catch((e) => setError(e?.message || "no se pudo guardar"));
  };
  return (
    <section data-mlx-config>
      <div className="mb-1 text-xs font-medium text-foreground">Configuración</div>
      <div className="flex flex-col gap-2 rounded border border-border px-2 py-2 text-xs">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(e) => update({ enabled: e.target.checked })} />
          <span>Activar routing con modelo local (mlx)</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted-foreground">Modelo</span>
          <input list="mlx-installed" value={model} onChange={(e) => update({ model: e.target.value })}
            placeholder="mlx-community/..." className="rounded border border-border bg-transparent px-2 py-1" />
          <datalist id="mlx-installed">
            {installed.map((m) => <option key={m.repoId} value={m.repoId} />)}
          </datalist>
        </label>
        <label className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Prompt del router</span>
            <button title="Volver al prompt por defecto" onClick={() => update({ routerPrompt: defaultPrompt })}
              className="text-[10px] text-muted-foreground hover:text-foreground">restaurar default</button>
          </div>
          <textarea value={routerPrompt} onChange={(e) => update({ routerPrompt: e.target.value })}
            rows={4} className="rounded border border-border bg-transparent px-2 py-1 font-mono text-[11px]" />
        </label>
        {error && <div className="text-[10px] text-destructive">{error}</div>}
        <div>
          <button title="Guardar la configuración" data-save-config onClick={save}
            className="rounded bg-primary px-2 py-1 text-[10px] text-primary-foreground">Guardar</button>
        </div>
      </div>
    </section>
  );
}
