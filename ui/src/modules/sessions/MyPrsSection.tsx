// ui/src/modules/sessions/MyPrsSection.tsx
import { ChevronRight } from "lucide-react";
import { Collapsible } from "radix-ui";
import { QueueList } from "../../components/ai-elements/queue";
import type { GhPr } from "../../transport/folderSessions";
import { Group, PrCard, useGithubReviews } from "./ReviewsSection";

const GROUPS = [
  ["returned", "Devueltas"], ["waiting", "Esperando revisores"], ["missing", "Sin revisores"],
  ["draft", "Draft"], ["approved", "Aprobadas"],
] as const;

/** Mis PRs abiertas de la org, agrupadas como el inbox de Graphite; cada card abre la PR. */
export function MyPrsSection() {
  const { gh, error } = useGithubReviews();
  const ghError = error ?? gh?.error;
  return (
    <Collapsible.Root defaultOpen className="group/myprs mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
          <ChevronRight size={13} className="transition-transform group-data-[state=open]/myprs:rotate-90" />
          Mis PRs
        </Collapsible.Trigger>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
      </div>
      <Collapsible.Content>
        {GROUPS.map(([key, label]) => {
          const prs: GhPr[] = gh?.mine?.[key] ?? [];
          return (
            <Group key={key} label={label} count={prs.length}>
              <QueueList>{prs.map((pr) => <PrCard key={pr.url} pr={pr} link />)}</QueueList>
            </Group>
          );
        })}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
