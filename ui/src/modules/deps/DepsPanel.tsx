// ui/src/modules/deps/DepsPanel.tsx
import { ExternalLink } from "lucide-react";
import { useFolders } from "../../state/folders";
import type { GhPr } from "../../transport/folderSessions";
import { allPrs, DepsList, useGithubReviews } from "../sessions/ReviewsSection";
import { desarrolloPrs } from "../github/GithubPanel";
import { repoShort } from "../sessions/DevCard";

const short = (repo: string | null) => (repo ?? "").replace(/^finnecto-/, "");

/** Módulo Dependencias: de qué depende cada PR del desarrollo y qué PRs dependen de ella. */
export function DepsPanel() {
  const { tree, activeId, activePrUrl } = useFolders();
  const session = tree.sessions.find((s) => s.id === activeId);
  const { gh, error } = useGithubReviews();
  const prs = gh ? desarrolloPrs(session, activePrUrl, gh) : [];
  const everyone = gh ? allPrs(gh) : [];
  return (
    <div className="flex w-full min-w-0 flex-col overflow-hidden">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Dependencias</div>
      {error && <p role="alert" className="mx-2.5 text-xs text-destructive">{error}</p>}
      {!session && !activePrUrl && <p className="mx-2.5 text-xs text-muted-foreground">Elige un desarrollo para ver sus dependencias.</p>}
      {(session || activePrUrl) && gh && prs.length === 0 && (
        <p className="mx-2.5 text-xs text-muted-foreground">Este desarrollo no tiene PRs abiertas.</p>)}
      {prs.map((pr) => {
        const dependents: GhPr[] = everyone.filter((p) => p.deps?.some((d) => d.url === pr.url && !d.via && !d.together));
        return (
          <div key={pr.url} className="mb-3 border-b border-border px-2.5 pb-2">
            <div className="font-mono text-[11px] font-bold tracking-wide">{repoShort(pr.repo)} #{pr.number}</div>
            <div className="truncate text-xs" title={pr.title}>{pr.title}</div>
            <div className="mt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
              Depende de {pr.depsPending ? <span className="normal-case text-amber-300">· faltan {pr.depsPending}</span> : null}</div>
            {pr.deps?.length ? <div className="mt-0.5"><DepsList pr={pr} /></div>
              : <p className="text-[11px] text-muted-foreground">Nada declarado en "## Dependencias".</p>}
            <div className="mt-2 text-[10px] uppercase tracking-wide text-muted-foreground">Dependen de esta</div>
            {dependents.length ? (
              <ul className="mt-0.5 space-y-0.5">
                {dependents.map((d) => (
                  <li key={d.url} className="group/c flex min-w-0 items-center gap-1.5 text-[11px]">
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{short(d.repo)}#{d.number}</span>
                    <span className="min-w-0 flex-1 truncate" title={d.title}>{d.title}</span>
                    <a href={d.url} target="_blank" rel="noreferrer" title="Abrir en GitHub" aria-label="Abrir en GitHub"
                      className="shrink-0 text-muted-foreground opacity-0 hover:text-foreground group-hover/c:opacity-100"><ExternalLink size={10} /></a>
                  </li>))}
              </ul>) : <p className="text-[11px] text-muted-foreground">Ninguna PR abierta la declara.</p>}
          </div>);
      })}
      <p className="mx-2.5 text-[10px] text-muted-foreground">
        ✓ mergeada · ◌ abierta (falta mergear) · ✗ cerrada · ⇄ van juntas · "vía X" = indirecta</p>
    </div>
  );
}
