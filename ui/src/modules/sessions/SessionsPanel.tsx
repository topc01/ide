import { useEffect } from "react";
import { Plus } from "lucide-react";
import { useSessions } from "../../state/sessions";
import { SessionNodeRow } from "./SessionNodeRow";
import { fetchTree } from "../../transport/sessions";
import { getWs } from "../../transport/wsClient";

const label = { fontSize: 10, textTransform: "uppercase" as const, letterSpacing: 0.6,
  color: "var(--text-muted)", margin: "10px 10px 4px" };

export function SessionsPanel() {
  const { tree, repos, setData, openModal } = useSessions();

  useEffect(() => {
    fetchTree(getWs()).then((d) => setData(d.sessions, d.repos)).catch(() => setData([], []));
  }, [setData]);

  return (
    <aside style={{ width: 272, background: "var(--panel-bg)", borderRight: "1px solid var(--border)",
      overflow: "auto", display: "flex", flexDirection: "column" }}>
      <div style={label}>Repos</div>
      {repos.map((r) => (
        <div key={r.id} style={{ display: "flex", justifyContent: "space-between",
          padding: "4px 10px", fontSize: 12 }}>
          <span>{r.name}</span>
          <span className="mono" style={{ color: "var(--accent)", fontSize: 11 }}>{r.branch}</span>
        </div>
      ))}

      <div style={{ ...label, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Sesiones</span>
        <Plus size={13} onClick={() => openModal(null)}
          style={{ cursor: "pointer", color: "var(--text-muted)" }} aria-label="Nueva sesión" />
      </div>
      {tree.map((n) => <SessionNodeRow key={n.id} node={n} depth={0} />)}

      <div
        onClick={() => openModal(null)}
        style={{ margin: "6px 10px", padding: "5px 8px", fontSize: 11, cursor: "pointer",
          color: "var(--text-muted)", border: "1px dashed var(--border)", borderRadius: 6 }}
      >
        + Agregar sesión
      </div>
    </aside>
  );
}
