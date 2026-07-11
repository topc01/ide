import { useEffect } from "react";
import { Plus } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { SessionNodeRow } from "./SessionNodeRow";
import { fetchTree } from "../../transport/sessions";
import { getWs } from "../../transport/wsClient";

const Label = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">
    {children}
  </div>
);

export function SessionsPanel() {
  const { tree, repos, setData, openModal } = useSessions();

  useEffect(() => {
    fetchTree(getWs()).then((d) => setData(d.sessions, d.repos)).catch(() => setData([], []));
  }, [setData]);

  return (
    <aside className="flex w-[272px] flex-col overflow-auto border-r border-border bg-card">
      <Label>Repos</Label>
      {repos.map((r) => (
        <div key={r.id} className="flex justify-between px-2.5 py-1 text-xs">
          <span>{r.name}</span>
          <span className="font-mono text-[11px] text-primary">{r.branch}</span>
        </div>
      ))}

      <div className="mx-2.5 mb-1 mt-2.5 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>Sesiones</span>
        <Plus
          size={13}
          onClick={() => openModal(null)}
          className="cursor-pointer text-muted-foreground"
          aria-label="Nueva sesión"
        />
      </div>
      {tree.map((n) => <SessionNodeRow key={n.id} node={n} depth={0} />)}

      <div
        onClick={() => openModal(null)}
        className="mx-2.5 my-1.5 cursor-pointer rounded-md border border-dashed border-border px-2 py-1.5 text-[11px] text-muted-foreground"
      >
        + Agregar sesión
      </div>
    </aside>
  );
}
