// ui/src/modules/sessions/MergeControls.tsx
import { useState } from "react";
import { GitMerge, RotateCw } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { QueueItemAction } from "../../components/ai-elements/queue";
import { mergePr, retryMerge, type GhPr, type MergeJob } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { cn } from "../../lib/utils";

/** Se puede mergear desde el IDE: aprobada y la de abajo de su stack (o sin stack). */
export const canMerge = (pr: GhPr) => pr.review === "approved" && (!pr.stack || pr.stack.position === 1);

/** Botón de hover: confirma y arma rebase + auto-merge (squash) + restack de las de arriba. */
export function MergeButton({ pr, above }: { pr: GhPr; above: number }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = pr.ci === "failure";
  const run = () => {
    setBusy(true); setError(null);
    mergePr(getWs(), pr.url).then(() => setOpen(false))
      .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setBusy(false));
  };
  return (<>
    <QueueItemAction aria-label={`Mergear ${pr.repo}#${pr.number}`} disabled={blocked}
      title={blocked ? "El CI falló (o hay conflicto): no se puede mergear" : "Mergear (rebase + auto-merge squash)"}
      onClick={(e) => { e.stopPropagation(); setError(null); setOpen(true); }}>
      <GitMerge size={11} />
    </QueueItemAction>
    <Dialog open={open} onOpenChange={(o) => !o && setOpen(false)}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader><DialogTitle>Mergear {pr.repo}#{pr.number}</DialogTitle></DialogHeader>
        <ol className="list-decimal space-y-1 pl-4 text-xs text-muted-foreground">
          <li>Rebasea <code>{pr.head}</code> sobre <code>{pr.base}</code> actualizada y la empuja (<code>--force-with-lease</code>).</li>
          <li>Arma el auto-merge con squash: GitHub mergea cuando pase el CI (nunca directo).</li>
          {above > 0
            ? <li>Cuando se mergee, restackea las {above} PRs de arriba del stack (rebase + push forzado; la de
                encima pasa a apuntar a <code>{pr.base}</code>) y borra <code>{pr.head}</code>.</li>
            : <li>Cuando se mergee, borra <code>{pr.head}</code>.</li>}
        </ol>
        {above > 0 && <p className="text-xs text-muted-foreground">
          Si tienes esas ramas abiertas en una sesión, después haz <code>git pull --rebase</code> ahí.</p>}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button title="Cerrar sin mergear" variant="ghost" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button title="Rebasear, empujar y armar el auto-merge (squash)" disabled={busy} onClick={run}>{busy ? "Rebaseando…" : "Mergear"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>);
}

/** Estado del merge armado desde el IDE (en la línea de detalle de la card). */
export function MergeStatus({ url, job }: { url: string; job?: MergeJob }) {
  const [error, setError] = useState<string | null>(null);
  if (!job) return null;
  const [label, cls] = {
    waiting: ["auto-merge ◌", "text-amber-300"], restacking: ["restack…", "text-sky-400"],
    done: ["mergeada ✓", "text-emerald-400"], error: ["⚠ merge", "text-destructive"],
  }[job.state];
  return (
    <span className={cn("flex items-center gap-1", cls)} title={job.error ?? error ?? undefined}>
      {label}
      {job.state === "error" && (
        <button aria-label="Reintentar merge" title={`Reintentar: ${job.error ?? ""}`}
          onClick={(e) => { e.stopPropagation(); retryMerge(getWs(), url).catch((x: any) => setError(x?.message ?? String(x))); }}
          className="hover:text-foreground"><RotateCw size={10} /></button>)}
    </span>
  );
}
