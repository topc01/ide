import { TabStrip } from "./TabStrip";
import { useStore } from "../state/store";

export function MainPanel() {
  const { openTabs, activeTabId } = useStore();
  const active = openTabs.find((t) => t.id === activeTabId);
  return (
    <main className="flex flex-1 flex-col bg-background">
      <TabStrip />
      <div className="min-h-0 flex-1 p-4 text-sm text-muted-foreground">
        {active ? `Tab: ${active.id}` : "Chat (R3)"}
      </div>
    </main>
  );
}
