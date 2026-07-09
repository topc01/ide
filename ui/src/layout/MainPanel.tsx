import { TabStrip } from "./TabStrip";
import { useStore } from "../state/store";

export function MainPanel() {
  const { activeTabId } = useStore();
  return (
    <main style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--app-bg)" }}>
      <TabStrip />
      <div style={{ flex: 1, padding: 16, color: "var(--text-secondary)" }}>
        {activeTabId === "chat" ? "Chat (R3)" : `Tab: ${activeTabId}`}
      </div>
    </main>
  );
}
