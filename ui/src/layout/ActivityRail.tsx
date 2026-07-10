import { useStore } from "../state/store";
import { getModules } from "../modules/registry";
import { cn } from "../lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "../components/ui/tooltip";

export function ActivityRail() {
  const { activePanel, setActivePanel } = useStore();
  return (
    <TooltipProvider delayDuration={300}>
      <nav className="flex w-11 flex-col items-center gap-1 border-r border-border bg-title-bg pt-2">
        {getModules().map((m) => {
          const Icon = m.icon, active = activePanel === m.id;
          return (
            <Tooltip key={m.id}>
              <TooltipTrigger asChild>
                <button
                  aria-label={m.title}
                  onClick={() => setActivePanel(m.id)}
                  className={cn(
                    "grid h-8 w-8 place-items-center rounded-md transition-colors",
                    active ? "bg-accent text-primary" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Icon size={16} strokeWidth={2} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">{m.title}</TooltipContent>
            </Tooltip>
          );
        })}
      </nav>
    </TooltipProvider>
  );
}
