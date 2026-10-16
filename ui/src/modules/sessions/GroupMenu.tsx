// ui/src/modules/sessions/GroupMenu.tsx
import { useState } from "react";
import { Layers } from "lucide-react";
import { getGroupers } from "./groupers";
import { useFolders } from "../../state/folders";
import { cn } from "../../lib/utils";

export function GroupMenu() {
  const { groupBy, setGroupBy } = useFolders();
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button aria-label="Agrupar" title="Agrupar" onClick={() => setOpen((o) => !o)}
        className={cn("grid h-5 w-5 place-items-center rounded text-muted-foreground hover:text-foreground",
          groupBy !== "none" && "text-primary")}>
        <Layers size={13} />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-10 mt-1 w-36 rounded-md border border-border bg-popover p-1 shadow">
          {getGroupers().map((g) => (
            <button title="Agrupar las sesiones así" key={g.id} role="menuitem" onClick={() => { setGroupBy(g.id); setOpen(false); }}
              className={cn("block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent",
                g.id === groupBy && "text-primary")}>
              {g.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
