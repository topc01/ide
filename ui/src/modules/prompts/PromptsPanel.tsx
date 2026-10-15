// ui/src/modules/prompts/PromptsPanel.tsx
import { useEffect, useState } from "react";
import { useFolders } from "../../state/folders";
import { fetchPrompts, type PromptInfo } from "../../transport/folderSessions";
import { typeIntoClaude } from "../../transport/terminalChannel";
import { getWs } from "../../transport/wsClient";

/** Lista `.ide/prompts/*.md`; click = pegar en el input de `claude` de la sesión abierta (sin enviar). */
export function PromptsPanel() {
  const session = useFolders((s) => s.tree.sessions.find((x) => x.id === s.activeId));
  const terminalId = session?.terminalId ?? null;
  const [prompts, setPrompts] = useState<PromptInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {          // se relee cada vez que se abre el panel
    fetchPrompts(getWs()).then((r) => setPrompts(r.prompts))
      .catch((e: any) => setError(e?.message ?? String(e)));
  }, []);

  const pick = (p: PromptInfo) => {
    if (!terminalId) return;
    setError(null);
    typeIntoClaude(getWs(), terminalId, p.text).catch((e: any) => setError(e?.message ?? String(e)));
  };

  return (
    <div className="flex flex-col">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Prompts</div>
      <p className="mx-2.5 mb-2 text-[11px] text-muted-foreground">
        {terminalId ? `Click = pegar en el input de ${session!.id} (sin enviar).`
          : "Abre una sesión (corriendo) para pegar un prompt."}
      </p>
      {error && <p role="alert" className="mx-2.5 text-xs text-destructive">{error}</p>}
      {!error && prompts === null && <p className="mx-2.5 text-xs text-muted-foreground">cargando…</p>}
      {prompts?.length === 0 && <p className="mx-2.5 text-xs text-muted-foreground">No hay prompts en .ide/prompts/</p>}
      {prompts?.map((p) => (
        <button key={p.name} title={p.text} disabled={!terminalId} onClick={() => pick(p)}
          className="mx-1 truncate rounded px-1.5 py-1 text-left text-xs hover:bg-accent disabled:opacity-50 disabled:hover:bg-transparent">
          {p.name}
        </button>
      ))}
    </div>
  );
}
