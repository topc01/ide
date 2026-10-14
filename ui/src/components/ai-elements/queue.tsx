// Port de AI Elements `Queue` (https://elements.ai-sdk.dev/components/queue): misma API,
// clases adaptadas a Tailwind 3 + tokens 1a.
import * as React from "react";
import { Collapsible } from "radix-ui";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export const Queue = ({ className, ...p }: React.ComponentProps<"div">) =>
  <div className={cn("flex flex-col gap-1", className)} {...p} />;

export const QueueSection = ({ defaultOpen = true, className, ...p }:
  React.ComponentProps<typeof Collapsible.Root>) =>
  <Collapsible.Root defaultOpen={defaultOpen} className={cn("group/section", className)} {...p} />;

export const QueueSectionTrigger = ({ className, children, ...p }: React.ComponentProps<"button">) => (
  <Collapsible.Trigger asChild>
    <button type="button" className={cn(
      "flex w-full items-center gap-1 px-2.5 py-1 text-[10px] uppercase tracking-wide",
      "text-muted-foreground hover:text-foreground", className)} {...p}>
      <ChevronRight size={12} className="transition-transform group-data-[state=open]/section:rotate-90" />
      {children}
    </button>
  </Collapsible.Trigger>
);

export const QueueSectionLabel = ({ label, count, icon, className }:
  { label: string; count?: number; icon?: React.ReactNode; className?: string }) => (
  <span className={cn("flex flex-1 items-center gap-1.5", className)}>
    {icon}<span>{label}</span>
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

export const QueueItemAction = ({ className, ...p }:
  Omit<React.ComponentProps<typeof Button>, "variant" | "size">) =>
  <Button variant="ghost" size="icon" className={cn("h-5 w-5", className)} {...p} />;
