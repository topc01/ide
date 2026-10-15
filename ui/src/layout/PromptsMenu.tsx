// ui/src/layout/PromptsMenu.tsx
import { useState } from "react";
import { MessageSquareText } from "lucide-react";
import { useFolders } from "../state/folders";
import { fetchPrompts, type PromptInfo } from "../transport/folderSessions";
import { typeIntoClaude } from "../transport/terminalChannel";
import { getWs } from "../transport/wsClient";
import { ActionButton } from "./ActionMenu";

/** Submenú del ActionMenu: pega un prompt de `.ide/prompts/` en el input de la sesión abierta. */
export function PromptsMenu() {
  const terminalId = useFolders((s) => s.tree.sessions.find((x) => x.id === s.activeId)?.terminalId ?? null);
  const [open, setOpen] = useState(false);
  const [prompts, setPrompts] = useState<PromptInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = () => {
    if (open) { setOpen(false); return; }
    setOpen(true); setError(null); setPrompts(null);
    fetchPrompts(getWs()).then((r) => setPrompts(r.prompts))
      .catch((e: any) => setError(e?.message ?? String(e)));
  };
  const pick = (p: PromptInfo) => {
    if (!terminalId) return;
    typeIntoClaude(getWs(), terminalId, p.text)
      .then(() => setOpen(false))
      .catch((e: any) => setError(e?.message ?? String(e)));
  };

  return (
    <div className="relative">
      <ActionButton label={terminalId ? "Prompts" : "Prompts (abre una sesión primero)"}
        icon={MessageSquareText} active={open} disabled={!terminalId} onClick={toggle} />
      {open && (
        <div role="menu" className="absolute left-full top-0 z-20 ml-1 w-56 rounded-md border border-border bg-popover p-1 shadow">
          <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">Prompts</div>
          {error && <p role="alert" className="px-2 py-1 text-xs text-destructive">{error}</p>}
          {!error && prompts === null && <p className="px-2 py-1 text-xs text-muted-foreground">cargando…</p>}
          {prompts?.length === 0 && (
            <p className="px-2 py-1 text-xs text-muted-foreground">No hay prompts en .ide/prompts/</p>
          )}
          {prompts?.map((p) => (
            <button key={p.name} role="menuitem" title={p.text} onClick={() => pick(p)}
              className="block w-full truncate rounded px-2 py-1 text-left text-xs hover:bg-accent">
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
