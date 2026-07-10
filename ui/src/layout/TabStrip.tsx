import { X } from "lucide-react";
import { useStore } from "../state/store";
import { cn } from "../lib/utils";

export function TabStrip() {
  const { openTabs, activeTabId, closeTab } = useStore();
  const tabCls = (active: boolean) =>
    cn("flex items-center gap-1.5 px-3 py-1.5 text-xs border-b-2",
       active ? "text-foreground border-primary" : "text-muted-foreground border-transparent");
  return (
    <div className="flex border-b border-border bg-title-bg">
      <div className={tabCls(activeTabId === "chat")}>Chat</div>
      {openTabs.map((t) => (
        <div key={t.id} className={tabCls(activeTabId === t.id)}>
          {t.label}
          <button aria-label={`cerrar ${t.label}`} onClick={() => closeTab(t.id)}
            className="text-muted-foreground hover:text-foreground"><X size={12} /></button>
        </div>
      ))}
    </div>
  );
}
