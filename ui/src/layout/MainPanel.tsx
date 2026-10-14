import { TabStrip } from "./TabStrip";
import { useStore } from "../state/store";
import { TerminalTab } from "../main/TerminalTab";
import { RegexAiTab } from "../main/RegexAiTab";
import { ChatView } from "../main/ChatView";
import { DiffTab } from "../main/DiffTab";
import { NotionPageTab } from "../main/NotionPageTab";
import { TaskTab } from "../main/TaskTab";
import { SessionView } from "../main/SessionView";
import { useFolders } from "../state/folders";

export function MainPanel() {
  const uiModules = useFolders((s) => s.uiModules);
  const { openTabs, activeTabId } = useStore();
  if (uiModules && !uiModules.includes("chat")) {
    return <main className="flex flex-1 flex-col bg-background"><SessionView /></main>;
  }
  const active = openTabs.find((t) => t.id === activeTabId);
  return (
    <main className="flex flex-1 flex-col bg-background">
      <TabStrip />
      <div className="min-h-0 flex-1">
        {active?.type === "terminal"
          ? <TerminalTab id={active.id} />
          : active?.type === "airegex"
            ? <RegexAiTab id={active.id} />
          : active?.type === "file"
            ? <DiffTab id={active.id} />
            : active?.type === "page"
              ? <NotionPageTab id={active.id} />
              : active?.type === "task"
                ? <TaskTab id={active.id} />
                : active
                  ? <div className="p-4 text-sm text-muted-foreground">{`Tab: ${active.id}`}</div>
                  : <ChatView />}
      </div>
    </main>
  );
}
