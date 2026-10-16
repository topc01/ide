// ui/src/modules/dev/DevPanel.tsx
import { useCurrentDev } from "../../main/currentDev";
import { PrRow } from "../sessions/MyDevsSection";
import { RepoLine } from "../sessions/RepoLine";
import { useGithubReviews } from "../sessions/ReviewsSection";
import { byRepoStack } from "../sessions/desarrollos";
import { DevTitle, repoShort } from "../sessions/DevCard";

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mx-2.5 mb-1 mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">{children}</div>;
}

/** Módulo Desarrollo: el detalle que no cabe en la card. Las PRs por repo y stack (review, CI, ⏸,
 *  Mergear en la de abajo de cada stack, sacar del desarrollo) y los worktrees de la sesión (rama,
 *  setup, scripts). */
export function DevPanel() {
  const dev = useCurrentDev();
  const { gh, error } = useGithubReviews();
  if (!dev) return <p className="p-3 text-xs text-muted-foreground">Elige un desarrollo.</p>;
  const s = dev.session;
  const groups = byRepoStack(dev.prs);
  const unlinkable = s && s.kind !== "review" ? s.id : undefined;
  return (
    <div className="flex h-full w-full min-w-0 flex-col overflow-auto pb-3 text-xs">
      <div className="mx-2.5 mt-2.5 flex text-sm">
        <DevTitle devKey={dev.key} prs={dev.prs}
          original={s?.title ?? dev.prs[0]?.title ?? s?.id ?? ""} />
      </div>
      {s && <div className="mx-2.5 font-mono text-[10px] text-muted-foreground">{s.id} · {s.kind}{s.status ? ` · ${s.status}` : ""}</div>}
      {error && <p role="alert" className="mx-2.5 mt-2 text-destructive">{error}</p>}

      <Label>PRs</Label>
      {dev.prs.length === 0 && <p className="mx-2.5 text-muted-foreground">{gh ? "Sin PRs abiertas." : "cargando…"}</p>}
      {groups.map((g) => (
        <div key={g.repo} className="mx-2.5 mb-2">
          <div className="mb-0.5 font-mono text-[10px] font-bold tracking-wide text-primary">{repoShort(g.repo)}</div>
          {g.stacks.map((st) => (
            <div key={st[0].url} className={st.length > 1 ? "mb-1 border-l border-border pl-1.5" : "mb-1"}
              title={st.length > 1 ? `stack de ${st.length} (de abajo hacia arriba)` : undefined}>
              {st.map((p, i) => <PrRow key={p.url} pr={p} job={gh?.merges?.[p.url]} bottom={i === 0} sessionId={unlinkable} />)}
            </div>))}
        </div>))}

      {s && s.kind !== "review" && (<>
        <Label>Worktrees</Label>
        {s.repos.length === 0 && <p className="mx-2.5 text-muted-foreground">La sesión no tiene repos (`ide repo add`).</p>}
        <div className="pr-2.5">{s.repos.map((r) => <RepoLine key={r.name} session={s} repo={r} />)}</div>
      </>)}
    </div>
  );
}
