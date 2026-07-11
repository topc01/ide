import { useStore } from "../state/store";
import { getModules } from "../modules/registry";
import { ScrollArea } from "../components/ui/scroll-area";

export function ContextPanel() {
  const { activePanel } = useStore();
  const mod = getModules().find((m) => m.id === activePanel);
  const Panel = mod?.Panel;
  return (
    <aside className="w-64 border-r border-border bg-card">
      <ScrollArea className="h-full">{Panel ? <Panel /> : null}</ScrollArea>
    </aside>
  );
}
