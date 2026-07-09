import { useStore } from "../state/store";

export function TabStrip() {
  const { openTabs, activeTabId, closeTab } = useStore();
  const tab = (id: string, label: string, closable: boolean) => {
    const active = activeTabId === id;
    return (
      <div key={id} style={{ padding: "6px 12px", fontSize: 12, display: "flex", gap: 6,
        color: active ? "var(--text-primary)" : "var(--text-muted)",
        borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent" }}>
        {label}{closable && <span onClick={() => closeTab(id)} style={{ cursor: "pointer" }}>×</span>}
      </div>
    );
  };
  return (
    <div style={{ display: "flex", background: "var(--title-bg)", borderBottom: "1px solid var(--border)" }}>
      {tab("chat", "Chat", false)}
      {openTabs.map((t) => tab(t.id, t.label, true))}
    </div>
  );
}
