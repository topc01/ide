// ui/src/modules/sessions/GroupedSection.tsx
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { ChevronRight, Settings2 } from "lucide-react";
import { Collapsible } from "radix-ui";
import { QueueList, QueueSection, QueueSectionContent, QueueSectionLabel, QueueSectionTrigger }
  from "../../components/ai-elements/queue";
import type { FolderSession, GhPr, GithubReviews } from "../../transport/folderSessions";
import { usePersistentOpen } from "../../lib/persist";
import { repoShort } from "./DevCard";
import { useSidebarConfig, type GroupBy } from "../../state/sidebarConfig";
import { useStore } from "../../state/store";
import { ACTIVITY } from "./activity";

/** Junto al nombre de un grupo: cuántos claude trabajan (◐) y cuántos te esperan (●); en 0 no se muestra.
 *  Una sesión con varias PRs (stack) cuenta una vez. */
function ActivityCounts({ items }: { items: Entry[] }) {
  const sessions = new Map(items.filter((e) => e.session?.process === "running").map((e) => [e.session!.id, e.session!]));
  const n = (st: "working" | "waiting") => [...sessions.values()].filter((s) => s.activity?.state === st).length;
  const parts = (["waiting", "working"] as const).map((st) => [st, n(st)] as const).filter(([, c]) => c > 0);
  if (!parts.length) return null;
  return (
    <span className="flex shrink-0 items-center gap-1.5 font-mono text-[10px] normal-case">
      {parts.map(([st, c]) => (
        <span key={st} className="flex items-center gap-0.5" title={`${c} ${st === "waiting" ? "te esperan" : "trabajando"}`}>
          <span aria-hidden className={cn("text-[9px]", ACTIVITY[st][1])}>{ACTIVITY[st][0]}</span>{c}
        </span>))}
    </span>
  );
}

/** Un ítem de una sección: una PR (con o sin sesión) o una sesión sin PR conocida. */
export interface Entry {
  key: string; pr?: GhPr; session?: FolderSession;
  status: string;                       // grupo por estado de la PR (id); el orden y nombre los da `statuses`
  render: () => ReactNode;
}

export type { GroupBy };
export const GROUP_LABEL: Record<GroupBy, string> = {
  status: "Por estado", repo: "Por repo", stack: "Por stack", author: "Por autor", none: "Sin agrupar",
};

const repoOf = (e: Entry) => e.pr?.repo
  ?? e.session?.prUrl?.match(/github\.com\/[^/]+\/([^/]+)\//)?.[1]
  ?? e.session?.repos[0]?.name ?? "sin repo";

function groupsOf(entries: Entry[], by: GroupBy, statuses: [string, string][], gh: GithubReviews | null) {
  const out = new Map<string, { label: string; items: Entry[] }>();
  const add = (k: string, label: string, e: Entry) => {
    if (!out.has(k)) out.set(k, { label, items: [] });
    out.get(k)!.items.push(e);
  };
  if (by === "status") {
    for (const [k, label] of statuses) out.set(k, { label, items: [] });     // orden fijo, aunque estén vacíos
    entries.forEach((e) => add(e.status, e.status, e));
  } else if (by === "repo") {
    [...entries].sort((a, b) => repoOf(a).localeCompare(repoOf(b)))
      .forEach((e) => add(repoOf(e), repoShort(repoOf(e)), e));
  } else if (by === "stack") {
    const sorted = [...entries].sort((a, b) => (a.pr?.stack?.position ?? 0) - (b.pr?.stack?.position ?? 0));
    sorted.filter((e) => e.pr?.stack).forEach((e) => {
      const st = e.pr!.stack!;
      const bottom = gh?.stacks?.[st.id]?.[0] ?? e.pr!;
      add(st.id, `${repoShort(e.pr!.repo)} · ${bottom.title}`, e);
    });
    sorted.filter((e) => !e.pr?.stack).forEach((e) => add("~none", "Sin stack", e));
  } else if (by === "author") {
    entries.forEach((e) => {
      const a = (e.pr?.author ?? e.session?.meta.author ?? "?").replace(/^@/, "");
      add(a, a, e);
    });
  } else {
    entries.forEach((e) => add("all", "Todas", e));
  }
  return [...out.entries()];
}

/** ⚙ de la sección: abre el módulo Configuración en la sidebar interna, enfocado en esta sección. */
export function ConfigButton({ id, title }: { id: string; title: string }) {
  const { activePanel, setActivePanel, innerSidebarOpen, toggleInnerSidebar } = useStore();
  const setFocus = useSidebarConfig((s) => s.setFocus);
  return (
    <button aria-label={`Configurar ${title}`} title={`Configurar ${title} (agrupar, filtros)`}
      onClick={() => {
        setFocus(id);
        if (activePanel !== "config") setActivePanel("config");
        if (!innerSidebarOpen) toggleInnerSidebar();
      }}
      className="grid h-5 w-5 place-items-center rounded text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
      <Settings2 size={13} />
    </button>
  );
}

/** Sección de la sidebar (Revisiones, Mis PRs): título colapsable con total, "agrupar por",
 *  grupos colapsables (recordados) y la misma card para todo. */
/** `hidden`: entradas ocultas; van aparte, en un grupo "Ocultos" al final (cerrado de entrada). */
/** `count` / `countTitle`: el número junto al título (default: el total). `groupActions`: un botón al
 *  lado del título de un grupo (por id de grupo), p.ej. "archivar todas" en Cerradas. */
export function GroupedSection({ id, title, entries, statuses, gh, headerExtra, beforeGroups, status, hidden = [],
  count, countTitle, groupActions }:
  { id: string; title: string; entries: Entry[]; statuses: [string, string][];
    gh: GithubReviews | null; headerExtra?: ReactNode; beforeGroups?: ReactNode; status?: ReactNode; hidden?: Entry[];
    count?: number; countTitle?: string; groupActions?: Record<string, ReactNode> }) {
  const [open, setOpen] = usePersistentOpen(id);
  const by = useSidebarConfig((s) => s.groupBy[id] ?? "status");
  const groups = groupsOf(entries, by, statuses, gh);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="group/sec mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger title="Colapsar / expandir la sección"
          className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
          <ChevronRight size={13} className="transition-transform group-data-[state=open]/sec:rotate-90" />
          {title}
        </Collapsible.Trigger>
        <span className="font-mono text-[11px] text-primary" title={countTitle ?? "total"}>{count ?? entries.length}</span>
        {status}
        <div className="ml-auto flex items-center gap-1">
          {headerExtra}
          <ConfigButton id={id} title={title} />
        </div>
      </div>
      <Collapsible.Content>
        {beforeGroups}
        {groups.filter(([, g]) => g.items.length).map(([key, g]) => (
          <QueueSection key={`${by}-${key}`} defaultOpen persistKey={`${id}.${by}.${key}`} className="mt-1">
            <div className="flex items-center">
              <QueueSectionTrigger title={g.label}>
                <QueueSectionLabel label={g.label} count={g.items.length} extra={<ActivityCounts items={g.items} />} className="min-w-0 [&>span:first-child]:truncate" />
              </QueueSectionTrigger>
              {groupActions?.[key]}
            </div>
            <QueueSectionContent><QueueList>{g.items.map((e) => <div key={e.key}>{e.render()}</div>)}</QueueList></QueueSectionContent>
          </QueueSection>))}
        {/* los grupos vacíos, juntos en uno (cerrado): apenas tienen algo vuelven a su lugar */}
        {groups.some(([, g]) => !g.items.length) && (
          <QueueSection defaultOpen={false} persistKey={`${id}.${by}.~empty`} className="mt-1 opacity-60">
            <QueueSectionTrigger title="Grupos sin nada por ahora">
              <QueueSectionLabel label="Vacíos" count={groups.filter(([, g]) => !g.items.length).length} />
            </QueueSectionTrigger>
            <QueueSectionContent>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 px-4 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                {groups.filter(([, g]) => !g.items.length).map(([key, g]) => <span key={key}>{g.label}</span>)}
              </div>
            </QueueSectionContent>
          </QueueSection>)}
        {hidden.length > 0 && (
          <QueueSection defaultOpen={false} persistKey={`${id}.hidden`} className="mt-1 opacity-70">
            <QueueSectionTrigger title="Desarrollos ocultos (el ojo de cada card los vuelve a mostrar)">
              <QueueSectionLabel label="Ocultos" count={hidden.length} extra={<ActivityCounts items={hidden} />} />
            </QueueSectionTrigger>
            <QueueSectionContent><QueueList>{hidden.map((e) => <div key={e.key}>{e.render()}</div>)}</QueueList></QueueSectionContent>
          </QueueSection>)}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
