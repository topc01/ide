// Port de AI Elements `Queue` (https://elements.ai-sdk.dev/components/queue): misma API,
// clases adaptadas a Tailwind 3 + tokens 1a.
import * as React from "react";
import { Collapsible } from "radix-ui";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { usePersistentOpen } from "@/lib/persist";

export const Queue = ({ className, ...p }: React.ComponentProps<"div">) =>
  <div className={cn("flex flex-col gap-1", className)} {...p} />;

/** `persistKey`: recuerda abierto/cerrado entre recargas (localStorage). */
/** `reveal`: cada vez que cambia a un valor no nulo, se abre (p.ej. tiene la card del desarrollo elegido). */
export const QueueSection = ({ defaultOpen = true, persistKey, reveal, className, ...p }:
  React.ComponentProps<typeof Collapsible.Root> & { persistKey?: string; reveal?: unknown }) => {
  const [open, setOpen] = usePersistentOpen(persistKey ?? "", defaultOpen);
  React.useEffect(() => { if (reveal != null && persistKey) setOpen(true); }, [reveal]);   // eslint-disable-line react-hooks/exhaustive-deps
  return persistKey
    ? <Collapsible.Root open={open} onOpenChange={setOpen} className={cn("group/section", className)} {...p} />
    : <Collapsible.Root defaultOpen={defaultOpen} className={cn("group/section", className)} {...p} />;
};

export const QueueSectionTrigger = ({ className, children, ...p }: React.ComponentProps<"button">) => (
  <Collapsible.Trigger asChild>
    <button title="Colapsar / expandir el grupo" type="button" className={cn(
      "flex w-full items-center gap-1 px-2.5 py-1 text-[10px] uppercase tracking-wide",
      "rounded text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground", className)} {...p}>
      <ChevronRight size={12} className="transition-transform group-data-[state=open]/section:rotate-90" />
      {children}
    </button>
  </Collapsible.Trigger>
);

export const QueueSectionLabel = ({ label, count, icon, extra, className }:
  { label: string; count?: number; icon?: React.ReactNode; extra?: React.ReactNode; className?: string }) => (
  <span className={cn("flex flex-1 items-center gap-1.5", className)}>
    {icon}<span>{label}</span>{extra}
    {count !== undefined && <span className="ml-auto font-mono text-[10px] text-primary">{count}</span>}
  </span>
);

export const QueueSectionContent = (p: React.ComponentProps<typeof Collapsible.Content>) =>
  <Collapsible.Content {...p} />;

export const QueueList = ({ className, ...p }: React.ComponentProps<"ul">) =>
  <ul className={cn("flex flex-col", className)} {...p} />;

export const QueueItem = ({ className, ...p }: React.ComponentProps<"li">) =>
  <li className={cn("group/item flex flex-col", className)} {...p} />;

export const QueueItemIndicator = ({ completed = false, className, ...p }:
  React.ComponentProps<"span"> & { completed?: boolean }) =>
  <span className={cn("inline-block h-2 w-2 shrink-0 rounded-full border border-muted-foreground",
    completed && "border-primary bg-primary", className)} {...p} />;

export const QueueItemContent = ({ completed = false, className, ...p }:
  React.ComponentProps<"span"> & { completed?: boolean }) =>
  <span className={cn("truncate text-xs", completed && "line-through opacity-50", className)} {...p} />;

export const QueueItemDescription = ({ completed = false, className, ...p }:
  React.ComponentProps<"span"> & { completed?: boolean }) =>
  <span className={cn("truncate text-[11px] text-muted-foreground", completed && "opacity-50", className)} {...p} />;

export const QueueItemActions = ({ className, ...p }: React.ComponentProps<"div">) =>
  <div className={cn("ml-auto flex items-center gap-0.5 opacity-0 group-hover/item:opacity-100", className)} {...p} />;

// botón de ícono: la explicación del hover sale del aria-label si no se pasa `title`
export const QueueItemAction = ({ className, title, ...p }:
  Omit<React.ComponentProps<typeof Button>, "variant" | "size">) =>
  <Button variant="ghost" size="icon-xs" className={className} title={title ?? p["aria-label"]} {...p} />;
