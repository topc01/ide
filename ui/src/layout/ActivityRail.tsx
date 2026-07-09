import { useStore } from "../state/store";
import { getModules } from "../modules/registry";

export function ActivityRail() {
  const { activePanel, setActivePanel } = useStore();
  return (
    <nav style={{ width: 44, background: "var(--title-bg)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8, gap: 4 }}>
      {getModules().map((m) => {
        const Icon = m.icon, active = activePanel === m.id;
        return (
          <button key={m.id} aria-label={m.title} title={m.title} onClick={() => setActivePanel(m.id)}
            style={{ width: 32, height: 32, display: "grid", placeItems: "center", border: "none",
              borderRadius: 6, cursor: "pointer",
              background: active ? "var(--selected-bg)" : "transparent",
              color: active ? "var(--accent)" : "var(--text-muted)" }}>
            <Icon size={16} strokeWidth={2} />
          </button>
        );
      })}
    </nav>
  );
}
