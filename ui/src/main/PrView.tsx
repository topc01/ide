// ui/src/main/PrView.tsx
import { useState } from "react";
import { ExternalLink, ScanEye } from "lucide-react";
import { useFolders } from "../state/folders";
import { newSessionForPr, startReview } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { Button } from "../components/ui/button";
import { PrDescription } from "./PrDescription";
import { allPrs, CiMark, DepsList, ReviewerChips, StackBadge, useGithubReviews } from "../modules/sessions/ReviewsSection";

/** Panel principal cuando el desarrollo es una PR sin sesión. */
export function PrView({ url }: { url: string }) {
  const { gh } = useGithubReviews();
  const setActive = useFolders((s) => s.setActive);
  const sessions = useFolders((s) => s.tree.sessions);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pr = gh ? allPrs(gh).find((p) => p.url === url) : undefined;
  if (!gh) return <div className="p-6 text-sm text-muted-foreground">cargando…</div>;
  if (!pr) return <div className="p-6 text-sm text-muted-foreground">La PR ya no está abierta.</div>;
  const toReview = gh.pending.some((p) => p.url === url);
  const link = useFolders.getState().tree.devPrs?.[pr.url];       // vinculada a una sesión (pegajoso)
  const hasSession = sessions.some((s) => s.id === pr.sessionId || s.prUrl === pr.url
    || (!!link && !link.out && s.id === link.sid));
  return (
    <div className="max-w-4xl p-6">
      <h1 className="text-base font-semibold">{pr.title}</h1>
      <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
        <span>{pr.repo}#{pr.number}</span><span>{pr.author}</span>
        {pr.head && <span>{pr.head} → {pr.base}</span>}
        <StackBadge pr={pr} /><CiMark pr={pr} />
      </div>
      <div className="-ml-4"><ReviewerChips pr={pr} /></div>
      {!!pr.deps?.length && (
        <div className="mt-4">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Dependencias</div>
          <DepsList pr={pr} />
        </div>)}
      <div className="mt-4 flex gap-2">
        <Button asChild variant="secondary" size="sm" title="Abrir la PR en GitHub">
          <a href={pr.url} target="_blank" rel="noreferrer"><ExternalLink size={13} /> Abrir en GitHub</a>
        </Button>
        {!hasSession && gh.me && pr.author === `@${gh.me}` && (
          <Button size="sm" variant="secondary" disabled={busy}
            title={`Sesión de claude con el worktree en la rama ${pr.head} (queda en este mismo desarrollo)`}
            onClick={() => {
              setBusy(true); setError(null);
              newSessionForPr(getWs(), pr.url).then((r) => setActive(r.session.id))
                .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setBusy(false));
            }}>
            {busy ? "Creando…" : "Crear sesión"}
          </Button>)}
        {toReview && (
          <Button size="sm" disabled={busy} title="Crear la sesión de revisión de esta PR y mandarle el prompt review-pr"
            onClick={() => {
              setBusy(true); setError(null);
              startReview(getWs(), pr.url).then((r) => setActive(r.id))
                .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setBusy(false));
            }}>
            <ScanEye size={13} /> {busy ? "Creando…" : "Revisar"}
          </Button>)}
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
      <PrDescription url={pr.url} />
      <p className="mt-4 text-xs text-muted-foreground">
        {hasSession ? "" : "Esta PR no tiene sesión. "}Comentarios y discusiones: módulo Revisión · stack: módulo Stack.</p>
    </div>
  );
}
