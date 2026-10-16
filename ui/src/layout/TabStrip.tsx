import { X } from "lucide-react";
import { useStore } from "../state/store";
import { cn } from "../lib/utils";

export function TabStrip() {
  const { openTabs, activeTabId, closeTab, setActiveTab } = useStore();
  const tabCls = (active: boolean) =>
    cn("flex shrink-0 items-center gap-1.5 whitespace-nowrap px-3 py-1.5 text-xs border-b-2 cursor-pointer",
       active ? "text-foreground border-primary" : "text-muted-foreground border-transparent");
  return (
    <div className="flex overflow-x-auto border-b border-border bg-title-bg">
      <div className={tabCls(activeTabId === "chat")} onClick={() => setActiveTab("chat")}>Chat</div>
      {openTabs.map((t) => (
        <div key={t.id} className={tabCls(activeTabId === t.id)} onClick={() => setActiveTab(t.id)}>
          {t.label}
          <button aria-label={`cerrar ${t.label}`} title={`cerrar ${t.label}`} onClick={(e) => { e.stopPropagation(); closeTab(t.id); }}
            className="text-muted-foreground hover:text-foreground"><X size={12} /></button>
        </div>
      ))}
    </div>
  );
}
