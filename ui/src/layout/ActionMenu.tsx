import type { ComponentType } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useStore } from "../state/store";
import { getModules } from "../modules/registry";
import { useFolders } from "../state/folders";
import { cn } from "../lib/utils";

export function ActionButton({ label, icon: Icon, active, onClick, disabled }: {
  label: string; icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  active?: boolean; onClick?: () => void; disabled?: boolean;
}) {
  return (
    <button aria-label={label} title={label} onClick={onClick} disabled={disabled}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-md transition-colors disabled:opacity-40",
        active ? "bg-accent text-primary" : "text-muted-foreground hover:text-foreground",
      )}>
      <Icon size={16} strokeWidth={2} />
    </button>
  );
}

export function ActionMenu() {
  const { activePanel, setActivePanel, innerSidebarOpen, toggleInnerSidebar } = useStore();
  const uiModules = useFolders((s) => s.uiModules);
  const visibleModules = () => getModules().filter((m) => !uiModules || uiModules.includes(m.id));
  return (
      <nav className="flex w-11 flex-col items-center gap-1 border-r border-border bg-title-bg pt-2">
        <ActionButton label={innerSidebarOpen ? "Colapsar sidebar interna" : "Expandir sidebar interna"}
          icon={innerSidebarOpen ? PanelLeftClose : PanelLeftOpen} onClick={toggleInnerSidebar} />
        {visibleModules().map((m) => (
          <ActionButton key={m.id} label={m.title} icon={m.icon} active={activePanel === m.id}
            onClick={() => { setActivePanel(m.id); if (!innerSidebarOpen) toggleInnerSidebar(); }} />
        ))}
      </nav>
  );
}
