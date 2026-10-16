import { useEffect } from "react";
import { ChevronRight } from "lucide-react";
import { Collapsible } from "radix-ui";
import { useSettings } from "../../state/settings";
import { fetchCustomizations } from "../../transport/settingsChannel";
import { getWs } from "../../transport/wsClient";
import { usePersistentOpen } from "../../lib/persist";

/** Sección Configuración de la sidebar (customizaciones de Claude Code: roles, agents, skills, …),
 *  con el mismo encabezado colapsable que Mis desarrollos y Revisiones. */
export function CustomizationsFooter() {
  const { items, setData, openSettings } = useSettings();
  const [open, setOpen] = usePersistentOpen("customizations");
  useEffect(() => {
    fetchCustomizations(getWs()).then(setData).catch(() => setData([]));
  }, [setData]);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="group/cfg mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger title="Colapsar / expandir la sección"
          className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
          <ChevronRight size={13} className="transition-transform group-data-[state=open]/cfg:rotate-90" />
          Configuración
        </Collapsible.Trigger>
        <span className="font-mono text-[11px] text-primary" title="total">{items.length}</span>
      </div>
      <Collapsible.Content className="py-1">
        {items.map((i) => (
          <button title={`Ver ${i.title}`} key={i.key} onClick={() => openSettings(i.key)}
            className="mx-1.5 flex w-[calc(100%-12px)] items-center justify-between rounded px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground">
            <span>{i.title}</span>
            {i.count > 0 && <span className="font-mono text-[10px]">{i.count}</span>}
          </button>
        ))}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
