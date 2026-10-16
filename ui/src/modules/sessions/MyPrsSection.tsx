// ui/src/modules/sessions/MyPrsSection.tsx
import { ChevronRight } from "lucide-react";
import { Collapsible } from "radix-ui";
import { QueueList, QueueSection, QueueSectionContent, QueueSectionLabel, QueueSectionTrigger }
  from "../../components/ai-elements/queue";
import type { GhPr } from "../../transport/folderSessions";
import { PrCard, useGithubReviews } from "./ReviewsSection";
import type { MergeJob } from "../../transport/folderSessions";
import { usePersistentOpen } from "../../lib/persist";

const GROUPS = [
  ["returned", "Devueltas"], ["waiting", "Esperando revisores"], ["missing", "Sin revisores"],
  ["draft", "Draft"], ["approved", "Aprobadas"],
] as const;

/** Mis PRs abiertas de la org, agrupadas como el inbox de Graphite; cada card abre la PR. */
export function MyPrsSection() {
  const { gh, error } = useGithubReviews();
  const [sectionOpen, setSectionOpen] = usePersistentOpen("myprs");
  // un server más viejo que la UI no manda `mine`: avisar en vez de mostrar ceros
  // merges cuya PR ya no está abierta (GitHub la mergeó): el restack y sus errores se ven acá
  const open = new Set(Object.values(gh?.mine ?? {}).flat().map((p) => p.url));
  // las mergeadas se ven (moradas) 24 h
  const recent = (j: MergeJob) => j.state !== "done" || (!!j.merged_at && Date.now() - Date.parse(j.merged_at) < 864e5);
  const orphans = Object.entries(gh?.merges ?? {}).filter(([url, j]) => !open.has(url) && recent(j));
  const ghError = error ?? gh?.error ?? (gh && !gh.mine ? "el server no manda tus PRs: reinicia `ide`" : null);
  return (
    <Collapsible.Root open={sectionOpen} onOpenChange={setSectionOpen} className="group/myprs mt-3 border-t border-border pt-2">
      <div className="flex items-center gap-1.5 px-2.5">
        <Collapsible.Trigger title="Colapsar / expandir la sección" className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary">
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
        {orphans.length > 0 && (
          <QueueSection defaultOpen persistKey="myprs.merges" className="mt-1">
            <QueueSectionTrigger><QueueSectionLabel label="Merges" count={orphans.length} /></QueueSectionTrigger>
            <QueueSectionContent>
              <QueueList>
                {orphans.map(([url, job]) => (
                  <PrCard key={url} merge={{ job, above: job.above?.length ?? 0 }} pr={{
                    url, title: job.title ?? url, number: job.number ?? 0, repo: job.repo ?? "", author: "",
                    draft: false, updatedAt: null, sessionId: "", head: null, base: null, review: null, stack: null }} />))}
              </QueueList>
            </QueueSectionContent>
          </QueueSection>)}
        {GROUPS.map(([key, label]) => {
          const prs: GhPr[] = gh?.mine?.[key] ?? [];
          return (
            <QueueSection key={key} defaultOpen persistKey={`myprs.${key}`} className="mt-1">
              <QueueSectionTrigger><QueueSectionLabel label={label} count={prs.length} /></QueueSectionTrigger>
              <QueueSectionContent>
                <QueueList>{prs.map((pr) => <PrCard key={pr.url} pr={pr} showReviewers
                  merge={{ job: gh?.merges?.[pr.url],
                           above: pr.stack ? pr.stack.size - pr.stack.position : 0 }} />)}</QueueList>
              </QueueSectionContent>
            </QueueSection>
          );
        })}
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
