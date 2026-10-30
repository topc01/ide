// ui/src/modules/sessions/MergeControls.tsx
import { useState } from "react";
import { GitMerge, RotateCw, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { QueueItemAction } from "../../components/ai-elements/queue";
import { cancelMerge, mergePr, retryMerge, type GhPr, type MergeJob } from "../../transport/folderSessions";
import { getWs } from "../../transport/wsClient";
import { DepsList } from "./ReviewsSection";
import { cn } from "../../lib/utils";

/** Se puede armar el merge desde el IDE: la de abajo de su stack (o sin stack). Aprobada o no: el
 *  auto-merge de GitHub espera la aprobación y el CI. En draft no (GitHub no lo acepta). */
export const canMerge = (pr: GhPr) => !pr.draft && (!pr.stack || pr.stack.position === 1);

/** Botón de hover: confirma y arma el auto-merge de GitHub (squash; rebase solo si hace falta) +
 *  restack de las de arriba. */
export function MergeButton({ pr, above }: { pr: GhPr; above: number }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // un conflicto ya no bloquea: se pone al día al mergear (si choca, el IDE le avisa a la sesión)
  const blocked = pr.ci === "failure";
  const run = () => {
    setBusy(true); setError(null);
    // solo valida y arranca: el progreso sigue en la card (no bloquea)
    mergePr(getWs(), pr.url).then(() => setOpen(false))
      .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setBusy(false));
  };
  return (<>
    <QueueItemAction aria-label={`Mergear ${pr.repo}#${pr.number}`} disabled={blocked}
      title={blocked ? "El CI falló: no se puede mergear"
        : pr.review === "approved" && pr.ci === "success" ? "Mergear (squash)" : "Armar auto-merge: GitHub la mergea al pasar el CI y la aprobación"}
      onClick={(e) => { e.stopPropagation(); setError(null); setOpen(true); }}>
      <GitMerge size={11} />
    </QueueItemAction>
    <Dialog open={open} onOpenChange={(o) => !o && setOpen(false)}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader><DialogTitle>Mergear {pr.repo}#{pr.number}</DialogTitle></DialogHeader>
        <ol className="list-decimal space-y-1 pl-4 text-xs text-muted-foreground">
          <li>Solo si hace falta (GitHub exige la rama al día, hay conflicto o arrastra commits de una PR ya
              mergeada), rebasea <code>{pr.head}</code> sobre <code>{pr.base}</code> y la empuja. Si no, no la toca
              (no vuelve a correr el CI).</li>
          <li>{pr.stack?.native
            ? "Stack nativo de GitHub: el IDE espera el CI y la aprobación y la mergea (squash); GitHub re-apunta las de arriba del stack nativo, y las que se le apilaron por base (fuera de él) las restackea el IDE cuando GitHub ya movió a su madre."
            : "Arma el auto-merge de GitHub (squash): GitHub la mergea al pasar el CI y la aprobación, aunque el IDE esté apagado."}
            {pr.review !== "approved" && " Todavía no está aprobada: queda esperando la aprobación."}</li>
          {pr.stack?.native ? null : above > 0
            ? <li>Cuando se mergee, restackea las {above} PRs de arriba del stack (rebase + push forzado; la de
                encima pasa a apuntar a <code>{pr.base}</code>) y borra <code>{pr.head}</code>.</li>
            : <li>Cuando se mergee, borra <code>{pr.head}</code>.</li>}
        </ol>
        <p className="text-xs text-muted-foreground">El diálogo se cierra al toque: el progreso se ve en la card
          (ámbar mergeando, rojo error, morado mergeada).</p>
        {above > 0 && !pr.stack?.native && <p className="text-xs text-muted-foreground">
          Si tienes esas ramas abiertas en una sesión, después haz <code>git pull --rebase</code> ahí.</p>}
        {!!pr.depsPending && (
          <div role="alert" className="rounded-md border border-amber-400/60 bg-amber-400/10 p-2">
            <p className="mb-1 text-xs font-semibold text-amber-300">
              ⚠ Faltan {pr.depsPending} dependencias por mergear (según "## Dependencias"):</p>
            <DepsList pr={pr} onlyPending />
          </div>)}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <DialogFooter>
          <Button title="Cerrar sin mergear" variant="ghost" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button title="Armar el auto-merge (squash; rebase solo si hace falta)" disabled={busy} onClick={run}>{busy ? "Iniciando…" : pr.depsPending ? "Armar igual" : pr.review === "approved" && pr.ci === "success" ? "Mergear" : "Armar auto-merge"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </>);
}

export const MERGE_ACTIVE: MergeJob["state"][] = ["rebasing", "waiting", "waiting_ci", "merging", "restacking"];

/** Borde/fondo de la card según el merge: ámbar mergeando, rojo error, morado mergeada. */
export function mergeCardClass(job?: MergeJob): string {
  if (!job) return "";
  if (job.state === "error") return "!border-solid !border-red-500 bg-red-500/10";
  if (job.state === "done") return "!border-solid !border-purple-500 bg-purple-500/10";
  return "!border-solid !border-amber-400 bg-amber-400/5";
}

const STEP: Record<MergeJob["state"], string> = {
  rebasing: "mergeando · rebasando", waiting_ci: "mergeando · esperando CI",
  waiting: "auto-merge armado", merging: "mergeando…", restacking: "mergeando · restack",
  done: "mergeada", error: "error al mergear",
};

/** Estado del merge armado desde el IDE (en la línea de detalle de la card). */
export function MergeStatus({ url, job }: { url: string; job?: MergeJob }) {
  const [error, setError] = useState<string | null>(null);
  if (!job) return null;
  const cls = job.state === "error" ? "text-red-500" : job.state === "done" ? "text-purple-400" : "text-amber-300";
  return (
    <span className={cn("flex items-center gap-1 font-semibold", cls)}
      title={job.error ?? error ?? (job.state === "done" ? "Mergeada en GitHub" : "Merge en curso")}>
      {MERGE_ACTIVE.includes(job.state) && <span className="animate-pulse">◌</span>}
      {job.state === "done" && "✓"}{job.state === "error" && "✗"} {STEP[job.state]}
      {(job.state === "waiting" || job.state === "waiting_ci") && (
        <button aria-label="Desarmar auto-merge" title="Desarmar el auto-merge (lo quita en GitHub; la PR queda abierta)"
          onClick={(e) => { e.stopPropagation(); cancelMerge(getWs(), url).catch((x: any) => setError(x?.message ?? String(x))); }}
          className="hover:text-foreground"><X size={10} /></button>)}
      {job.state === "error" && (
        <button aria-label="Reintentar merge" title={`Reintentar: ${job.error ?? ""}`}
          onClick={(e) => { e.stopPropagation(); retryMerge(getWs(), url).catch((x: any) => setError(x?.message ?? String(x))); }}
          className="hover:text-foreground"><RotateCw size={10} /></button>)}
    </span>
  );
}
