import { useStore } from "../state/store";

export function Sidebar() {
  const { repos } = useStore();
  return (
    <aside style={{ width: 272, background: "var(--panel-bg)", borderRight: "1px solid var(--border)", padding: 10 }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--text-muted)", marginBottom: 6 }}>Repos</div>
      {repos.map((r) => (
        <div key={r.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 6px", borderRadius: 6 }}>
          <span>{r.name}</span>
          <span className="mono" style={{ color: "var(--accent)", fontSize: 11 }}>{r.branch}</span>
        </div>
      ))}
    </aside>
  );
}
