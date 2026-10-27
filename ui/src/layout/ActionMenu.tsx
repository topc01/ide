import type { ComponentType } from "react";
import { Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-react";
import { useStore } from "../state/store";
import { getModules, type ActivityModule } from "../modules/registry";
import { useFolders } from "../state/folders";
import { cn } from "../lib/utils";
import { useTheme } from "../state/theme";

export function ActionButton({ label, icon: Icon, active, onClick, disabled, badge }: {
  label: string; icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  active?: boolean; onClick?: () => void; disabled?: boolean; badge?: number | null;
}) {
  return (
    <button aria-label={label} title={badge ? `${label} (${badge})` : label} onClick={onClick} disabled={disabled}
      className={cn(
        "relative grid h-8 w-8 place-items-center rounded-md transition-colors disabled:opacity-40",
        active ? "bg-accent text-primary" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}>
      <Icon size={16} strokeWidth={2} />
      {!!badge && <span className="absolute -right-0.5 -top-0.5 min-w-[14px] rounded-full bg-primary px-1 text-center font-mono text-[9px] font-bold leading-[14px] text-primary-foreground">
        {badge > 99 ? "99+" : badge}</span>}
    </button>
  );
}

/** Un módulo en el menú: con su conteo si lo tiene (`useBadge`). */
function ModuleButton({ m, active, onClick }: { m: ActivityModule; active: boolean; onClick: () => void }) {
  const badge = m.useBadge?.() ?? null;
  return <ActionButton label={m.title} icon={m.icon} active={active} onClick={onClick} badge={badge} />;
}

export function ActionMenu() {
  const { activePanel, setActivePanel, innerSidebarOpen, toggleInnerSidebar } = useStore();
  const uiModules = useFolders((s) => s.uiModules);
  const { theme, toggle } = useTheme();
  const visibleModules = () => getModules().filter((m) => !uiModules || uiModules.includes(m.id));
  return (
      <nav className="flex w-11 flex-col items-center gap-1 border-r border-border bg-title-bg pt-2">
        <ActionButton label={innerSidebarOpen ? "Colapsar sidebar interna" : "Expandir sidebar interna"}
          icon={innerSidebarOpen ? PanelLeftClose : PanelLeftOpen} onClick={toggleInnerSidebar} />
        {visibleModules().map((m) => (
          <ModuleButton key={m.id} m={m} active={activePanel === m.id}
            onClick={() => { setActivePanel(m.id); if (!innerSidebarOpen) toggleInnerSidebar(); }} />
        ))}
        <div className="mt-auto pb-2">
          <ActionButton label={theme === "light" ? "Pasar a modo oscuro" : "Pasar a modo claro"}
            icon={theme === "light" ? Moon : Sun} onClick={toggle} />
        </div>
      </nav>
  );
}
