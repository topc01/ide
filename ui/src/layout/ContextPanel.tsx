import { useStore } from "../state/store";
import { getModules } from "../modules/registry";
import { useFolders } from "../state/folders";
import { ScrollArea } from "../components/ui/scroll-area";

export function ContextPanel() {
  const { activePanel } = useStore();
  const uiModules = useFolders((s) => s.uiModules);
  const visible = getModules().filter((m) => !uiModules || uiModules.includes(m.id));
  if (visible.length === 0) return null;
  const mod = visible.find((m) => m.id === activePanel) ?? visible[0];
  const Panel = mod?.Panel;
  return (
    <aside className="w-64 border-r border-border bg-card">
      <ScrollArea className="h-full">{Panel ? <Panel /> : null}</ScrollArea>
    </aside>
  );
}
