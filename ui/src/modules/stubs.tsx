import { Search, FileDiff, Layers, ListChecks, SquareTerminal, BookOpen } from "lucide-react";
import { registerModule, getModules } from "./registry";

const Stub = (label: string): React.FC => () => (
  <div style={{ padding: 12, color: "var(--text-muted)" }}>{label} — próximamente</div>
);

registerModule({ id: "search", title: "Search", icon: Search, Panel: Stub("Search") });
registerModule({ id: "changes", title: "Changed files", icon: FileDiff, Panel: Stub("Changed files") });
registerModule({ id: "graphite", title: "Graphite", icon: Layers, Panel: Stub("Graphite") });
registerModule({ id: "tasks", title: "Tasks", icon: ListChecks, Panel: Stub("Tasks") });
registerModule({ id: "terminal", title: "Terminal", icon: SquareTerminal, Panel: Stub("Terminal") });
registerModule({ id: "notion", title: "Notion", icon: BookOpen, Panel: Stub("Notion") });

export { getModules };
