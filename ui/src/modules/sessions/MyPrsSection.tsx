// ui/src/modules/sessions/MyPrsSection.tsx
import { ChevronRight } from "lucide-react";
import { Collapsible } from "radix-ui";
import { QueueList, QueueSection, QueueSectionContent, QueueSectionLabel, QueueSectionTrigger }
  from "../../components/ai-elements/queue";
import type { GhPr } from "../../transport/folderSessions";
import { PrCard, useGithubReviews } from "./ReviewsSection";
import { GroupedSection, type Entry } from "./GroupedSection";
import type { MergeJob } from "../../transport/folderSessions";
import { usePersistentOpen } from "../../lib/persist";

type MineKey = "returned" | "waiting" | "missing" | "draft" | "approved";
const GROUPS: [MineKey, string][] = [
  ["returned", "Devueltas"], ["waiting", "Esperando revisores"], ["missing", "Sin revisores"],
  ["draft", "Draft"], ["approved", "Aprobadas"],
];

/** Mis PRs abiertas de la org, agrupadas como el inbox de Graphite; cada card abre la PR. */
export function MyPrsSection() {
  const { gh, error } = useGithubReviews();
  // merges cuya PR ya no está abierta (GitHub la mergeó): el restack y sus errores se ven acá
  const open = new Set(Object.values(gh?.mine ?? {}).flat().map((p) => p.url));
  // las mergeadas se ven (moradas) 24 h
  const recent = (j: MergeJob) => j.state !== "done" || (!!j.merged_at && Date.now() - Date.parse(j.merged_at) < 864e5);
  const orphans = Object.entries(gh?.merges ?? {}).filter(([url, j]) => !open.has(url) && recent(j));
  // un server más viejo que la UI no manda `mine`: avisar en vez de mostrar ceros
  const ghError = error ?? gh?.error ?? (gh && !gh.mine ? "el server no manda tus PRs: reinicia `ide`" : null);

  const entries: Entry[] = [
    ...orphans.map(([url, job]): Entry => {
      const pr: GhPr = { url, title: job.title ?? url, number: job.number ?? 0, repo: job.repo ?? "", author: "",
        draft: false, updatedAt: null, sessionId: "", head: null, base: null, review: null, stack: null };
      return { key: url, pr, status: "merges", render: () => <PrCard pr={pr} merge={{ job, above: job.above?.length ?? 0 }} /> };
    }),
    ...GROUPS.flatMap(([key]) => (gh?.mine?.[key] ?? []).map((pr: GhPr): Entry => ({
      key: pr.url, pr, status: key, render: () => <PrCard pr={pr} showReviewers
        merge={{ job: gh?.merges?.[pr.url], above: pr.stack ? pr.stack.size - pr.stack.position : 0 }} />,
    }))),
  ];

  return (
    <GroupedSection id="myprs" title="Mis PRs" entries={entries} gh={gh}
      statuses={[...(orphans.length ? [["merges", "Merges"] as [string, string]] : []), ...GROUPS]}
      status={<>
        {ghError && <span role="alert" className="truncate text-[10px] text-destructive"
          title={`${ghError} (último OK: ${gh?.lastOk ?? "nunca"})`}>⚠ github</span>}
        {!gh && !ghError && <span className="text-[10px] text-muted-foreground">cargando…</span>}
      </>} />
  );
}
