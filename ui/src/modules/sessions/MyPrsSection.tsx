// ui/src/modules/sessions/MyPrsSection.tsx
import { ChevronRight } from "lucide-react";
import { Collapsible } from "radix-ui";
import { QueueList, QueueSection, QueueSectionContent, QueueSectionLabel, QueueSectionTrigger }
  from "../../components/ai-elements/queue";
import type { GhPr } from "../../transport/folderSessions";
import { PrCard, useGithubReviews } from "./ReviewsSection";

const GROUPS = [
  ["returned", "Devueltas"], ["waiting", "Esperando revisores"], ["missing", "Sin revisores"],
  ["draft", "Draft"], ["approved", "Aprobadas"],
] as const;

/** Mis PRs abiertas de la org, agrupadas como el inbox de Graphite; cada card abre la PR. */
export function MyPrsSection() {
  const { gh, error } = useGithubReviews();
  // un server más viejo que la UI no manda `mine`: avisar en vez de mostrar ceros
  const ghError = error ?? gh?.error ?? (gh && !gh.mine ? "el server no manda tus PRs: reinicia `ide`" : null);
  return (
    <Collapsible.Root defaultOpen className="group/myprs mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
          <ChevronRight size={13} className="transition-transform group-data-[state=open]/myprs:rotate-90" />
          Mis PRs
        </Collapsible.Trigger>
        {gh?.mine && <span className="font-mono text-[11px] text-primary" aria-label="total de mis PRs">
          {GROUPS.reduce((n, [key]) => n + (gh.mine[key]?.length ?? 0), 0)}</span>}
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
      </div>
      <Collapsible.Content>
        {GROUPS.map(([key, label]) => {
          const prs: GhPr[] = gh?.mine?.[key] ?? [];
          return (
            <QueueSection key={key} defaultOpen className="mt-1">
              <QueueSectionTrigger><QueueSectionLabel label={label} count={prs.length} /></QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList>{prs.map((pr) => <PrCard key={pr.url} pr={pr} />)}</QueueList>
              </QueueSectionContent>
            </QueueSection>
          );
        })}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
