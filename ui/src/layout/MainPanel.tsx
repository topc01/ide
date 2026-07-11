import { TabStrip } from "./TabStrip";
import { useStore } from "../state/store";
import { TerminalTab } from "../main/TerminalTab";

export function MainPanel() {
  const { openTabs, activeTabId } = useStore();
  const active = openTabs.find((t) => t.id === activeTabId);
  return (
    <main className="flex flex-1 flex-col bg-background">
      <TabStrip />
      <div className="min-h-0 flex-1">
        {active?.type === "terminal"
          ? <TerminalTab id={active.id} />
          : <div className="p-4 text-sm text-muted-foreground">{active ? `Tab: ${active.id}` : "Chat (R3)"}</div>}
      </div>
    </main>
  );
}
