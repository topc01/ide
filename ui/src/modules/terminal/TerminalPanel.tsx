import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";
import type { SessionNode } from "../../transport/sessions";
import { openTerminal } from "../../transport/terminalChannel";
import { getWs } from "../../transport/wsClient";
import { Button } from "../../components/ui/button";

const Label = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">
    {children}
  </div>
);

function find(tree: SessionNode[], id: string | null): SessionNode | null {
  if (!id) return null;
  for (const n of tree) {
    if (n.id === id) return n;
    const found = find(n.children, id);
    if (found) return found;
  }
  return null;
}

export function TerminalPanel() {
  const { tree, activeSessionId } = useSessions();
  const openTab = useStore((s) => s.openTab);
  const session = find(tree, activeSessionId);

  async function handleOpenTerminal() {
    if (!session) return;
    const { id } = await openTerminal(getWs(), { sessionId: session.id });
    openTab({ id, type: "terminal", label: "zsh" });
  }

  return (
    <aside className="w-64 overflow-auto border-r border-border bg-card">
      <Label>Terminal</Label>
      {session ? (
        <div className="mx-2.5 flex flex-col gap-2">
          <div className="rounded-md border border-border bg-terminal-bg p-2">
            <div className="text-xs text-foreground">{session.name}</div>
            <div className="font-mono text-[11px] text-muted-foreground">{session.worktreePath}</div>
          </div>
          <Button onClick={handleOpenTerminal}>Abrir terminal</Button>
        </div>
      ) : (
        <div className="mx-2.5 text-[11px] text-muted-foreground">
          Seleccioná una sesión para abrir su terminal.
        </div>
      )}
    </aside>
  );
}
