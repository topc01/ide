import { Dialog, DialogContent } from "../../components/ui/dialog";
import { Badge } from "../../components/ui/badge";
import { cn } from "../../lib/utils";
import { useSettings } from "../../state/settings";

export function SettingsModal() {
  const { items, open, selectedKey, openSettings, closeSettings } = useSettings();
  const item = items.find((i) => i.key === selectedKey) ?? items[0];
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) closeSettings(); }}>
      <DialogContent className="flex h-[540px] max-w-[760px] gap-0 p-0 sm:max-w-[760px]">
        <nav className="w-[212px] shrink-0 border-r border-border bg-card p-2">
          {items.map((i) => (
            <button key={i.key} onClick={() => openSettings(i.key)}
              className={cn("flex w-full items-center justify-between rounded px-2 py-1.5 text-xs",
                i.key === selectedKey ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
              <span>{i.title}</span>
              {i.count > 0 && <span className="text-[10px] text-muted-foreground">{i.count}</span>}
            </button>
          ))}
        </nav>
        <div className="min-w-0 flex-1 overflow-auto p-4">
          {item && (
            <>
              <div className="text-base font-medium text-foreground">{item.title}</div>
              <div className="mb-3 text-xs text-muted-foreground">{item.description}</div>
              {item.rows.length === 0 ? (
                <div className="text-xs text-muted-foreground">No configurado.</div>
              ) : (
                <div className="flex flex-col gap-1">
                  {item.rows.map((r, idx) => (
                    <div key={idx} data-row className="flex items-center justify-between rounded border border-border px-2 py-1.5 text-xs">
                      <span>{r.label}</span>
                      {r.inUse && <Badge variant="secondary" className="bg-role-pill text-primary text-[10px]">en uso</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
