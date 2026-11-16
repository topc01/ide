// ui/src/modules/sessions/SessionItem.tsx
import { useState, type ReactNode } from "react";
import { Archive, ExternalLink, Play } from "lucide-react";
import { freezeSession, type FolderSession, type GhPr } from "../../transport/folderSessions";
import { CardMeta, CiMark } from "./ReviewsSection";
import { CardActions, CardCorner, DevIndex, TicketChip, RelationChips, LaterChip, DevStateLabel, RenameAction, StateAction, CardShell, DepsPause, DevTitle, RefChip, devTone, repoShort, titlePad } from "./DevCard";
import { byRepoStack, worstPr } from "./desarrollos";
import { ago, STATE, type Block, type DevStateInfo } from "./devStates";
import { ACTIVITY, activityOf, waitTime } from "./activity";
import { PersonChip } from "../../lib/people";
import { getWs } from "../../transport/wsClient";

import { useFolders } from "../../state/folders";
import { QueueItem, QueueItemActions, QueueItemAction } from "../../components/ai-elements/queue";
import { Badge } from "../../components/ui/badge";
import { ConfirmArchiveDialog } from "./ConfirmArchiveDialog";
import { cn } from "../../lib/utils";
import { usePersistentOpen } from "../../lib/persist";


/** `pr`: la PR de GitHub de la sesión (si se conoce): agrega su posición en el stack.
 *  `onlyActions`: el hover muestra solo `actions` (sin parar/archivar). */
/** "https://github.com/o/finnecto-api/pull/4581" → "API #4581" (PR ya cerrada: sin datos de GitHub). */
function prLabel(url?: string | null): string | null {
  const m = url?.match(/github\.com\/[^/]+\/([^/]+)\/pull\/(\d+)/);
  return m ? `${repoShort(m[1])} #${m[2]}` : null;
}

/** `prs`: las PRs del desarrollo de la sesión (Mis desarrollos); con más de una se muestran como filas. */
/** `noArchive`: sin botón archivar (p.ej. revisiones donde pediste cambios: siguen vivas). */
/** `dev`: estado del desarrollo (Mis desarrollos): se muestra y colorea la card si la sección agrupa por él. */
/** `merged`: sus PRs ya mergeadas (chips moradas). */
export function SessionItem({ session, actions, pr: prProp, prs, onlyActions = false, noArchive = false, dev, merged = [], extra }:
  { session: FolderSession; actions?: ReactNode; pr?: GhPr; prs?: GhPr[]; onlyActions?: boolean; noArchive?: boolean;
    dev?: DevStateInfo | null; merged?: GhPr[]; extra?: ReactNode }) {
  const pr = prProp ?? prs?.[0];
  const many = (prs?.length ?? 0) > 1;
  const { activeId, activePrUrl, setActive } = useFolders();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = activityOf(session, dev);
  const [dot, dotCls, label] = ACTIVITY[act];
  const waitNote = act === "waiting" || act === "outdated" ? session.activity?.note : null;
  const outdated = act === "outdated" ? session.activity?.outdated : null;
  // varias PRs (stack o fullstack): el tono y el CI los da la peor
  const worst = many ? worstPr(prs!) : { review: pr, ci: pr };
  const tone = devTone(worst.review, undefined, { merged: session.prState === "merged", status: session.status });
  const groups = many ? byRepoStack(prs!) : [];
  const repos = [...new Set([...session.repos.map((r) => r.name), ...(prs ?? []).map((p) => p.repo)])].sort();
  const isReview = session.kind === "review";
  // revisión en pausa (p.ej. esperando tu OK para publicar): va encima del veredicto
  const pause = useFolders((st) => isReview ? st.tree.devStates?.[`s:${session.id}`] : undefined);
  return (
    <QueueItem className="px-2 py-1">
      {/* con una PR (sin sesión) elegida, la sesión anterior ya no es el desarrollo activo */}
      <CardShell tone={tone} dev={dev} onClick={() => setActive(session.id)}
        selected={activeId === session.id && !activePrUrl || !!prs?.some((p) => p.url === activePrUrl)}>
        <CardCorner><DepsPause pr={pr} />{worst.ci && <CiMark pr={worst.ci} />}</CardCorner>
        <div className={cn("flex items-start gap-1.5", titlePad(pr))}>
          {act === "frozen" ? (
            // congelar ya no se ofrece; las que quedaron congeladas de antes se sueltan aquí
            <button aria-label="Soltar" title={`${label}. Click: soltarla (sigue donde estaba)`}
              onClick={(e) => { e.stopPropagation(); freezeSession(getWs(), session.id, false).catch((err: any) => setError(err?.message ?? String(err))); }}
              className="group/dot grid w-3 shrink-0 place-items-center">
              <span className={cn(dotCls, "group-hover/dot:hidden")}>{dot}</span>
              <Play size={11} className="hidden text-violet-400 group-hover/dot:block" />
            </button>
          ) : (
          <span aria-label={label} title={`${label}${session.activity?.since && session.process === "running"
            ? ` (desde ${new Date(session.activity.since).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })})` : ""}${waitNote ? `\n${waitNote}` : ""}`}
            className={dotCls}>{dot}</span>)}
          <DevTitle devKey={`s:${session.id}`} prs={prs ?? (pr ? [pr] : [])}
            original={session.title ?? pr?.title ?? prLabel(session.prUrl) ?? session.id} />
          {(session.error || session.launchError) && (
            <span title={session.error ?? session.launchError ?? ""} className="text-destructive">⚠</span>)}
          {error && <span role="alert" title={error} className="text-destructive">⚠</span>}
          <CardActions>
            <RenameAction devKey={`s:${session.id}`} />
            <StateAction dev={dev} devKey={`s:${session.id}`} />
            {actions}
            {/* toda card con PR se puede abrir en GitHub (las pendientes ya lo traen en `actions`) */}
            {!onlyActions && (pr?.url ?? session.prUrl) && (
              <QueueItemAction aria-label={`Abrir ${session.id} en GitHub`} title="Abrir la PR en GitHub" asChild>
                <a href={pr?.url ?? session.prUrl ?? ""} target="_blank" rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}><ExternalLink size={11} /></a>
              </QueueItemAction>)}
            {!onlyActions && !noArchive && (
              <QueueItemAction aria-label={`Archivar ${session.id}`} title="Archivar"
                onClick={(e) => { e.stopPropagation(); setConfirm(true); }}>
                <Archive size={11} />
              </QueueItemAction>)}
          </CardActions>
        </div>
        {/* repos con su número: una chip por PR (con varias, por repo: las filas dan los números) */}
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <DevIndex devKey={`s:${session.id}`} prs={prs ?? (pr ? [pr] : [])} />
          {session.kind === "ticket" && <TicketChip devKey={`s:${session.id}`} />}
          {session.kind === "ticket" && <RelationChips devKey={`s:${session.id}`} />}
          {session.model && (
            <span title={`Su claude usa el modelo ${session.model} (cambiarlo: ide session model ${session.id} <modelo>)`}
              className="rounded border border-border px-1 font-mono text-[10px] text-muted-foreground">{session.model}</span>)}
          {many ? groups.flatMap((g) => g.stacks.flat()).map((p) => <RefChip key={p.url} repo={p.repo} number={p.number} pr={p} />)
            : pr ? <RefChip repo={pr.repo} number={pr.number} pr={pr} />
            : merged.length ? null
            : prLabel(session.prUrl) ? <span className="rounded border border-border px-1 font-mono text-[10px] font-bold">{prLabel(session.prUrl)}</span>
            : repos.length ? repos.map((r) => <RefChip key={r} repo={r} />)
            : /^\d+$/.test(session.id) ? null   // el id es el número (#n): ya se ve
            : <span className="font-mono text-[10px] text-muted-foreground">{session.id}</span>}
          {merged.length > 0 && <MergedToggle id={session.id} merged={merged} hasOpen={many || !!pr} />}
          {session.kind === "ticket" && !pr && !many && !merged.length && dev && dev.phase !== "investigating" && dev.phase !== "merged" && (
            <span className="rounded border border-dashed border-border px-1 text-[10px] text-muted-foreground"
              title="Ya pasó de investigando, pero no tiene ninguna PR abierta">sin PR</span>)}
          <LaterChip devKey={`s:${session.id}`} prs={prs ?? (pr ? [pr] : [])} />
          {isReview && session.meta.author && <PersonChip login={session.meta.author} title={`autor: ${session.meta.author}`} />}
        </div>
        <CardMeta>
          {extra}
          {act === "waiting" && (waitNote || waitTime(session)) && (
            <span className="line-clamp-2 basis-full text-orange-300"
              title={`Claude terminó el turno a las ${waitTime(session) ?? "?"}${waitNote ? `\nÚltimo mensaje: ${waitNote}` : ""}`}>
              › {waitTime(session) && <span className="font-mono text-orange-300/80">{waitTime(session)}</span>}{waitNote ? ` ${waitNote}` : ""}</span>)}
          {outdated && (
            <span className="line-clamp-2 basis-full text-muted-foreground"
              title={`Te esperaba desde las ${waitTime(session) ?? "?"}; a las ${outdated.at} ${outdated.what}: probablemente ya no te espera.`
                + `${waitNote ? `\nSu último mensaje: ${waitNote}` : ""}\n(vuelve a «te espera» cuando termine otro turno)`}>
              › <span className="font-mono">{outdated.at}</span> {outdated.what} · <span className="line-through">{waitNote}</span></span>)}
          {dev && <DevStateLabel dev={dev} devKey={`s:${session.id}`} />}
          {isReview && pause?.block && (
            <span className="block basis-full" title={`La sesión de revisión está en pausa: ${STATE[pause.block as Block]?.[0] ?? pause.block}`
              + `${pause.note ? `\nNota: ${pause.note}` : ""}\n(la sesión la quita al seguir)`}>
              <span className={cn("rounded-sm border border-current px-1.5 text-[10px] font-semibold uppercase tracking-wide",
                STATE[pause.block as Block]?.[2])}>{STATE[pause.block as Block]?.[0] ?? pause.block}</span>
              {pause.since && <span className="ml-1.5 text-muted-foreground">hace {ago(pause.since)}</span>}
              {pause.note && <span className="line-clamp-2 italic text-muted-foreground">{pause.note}</span>}
            </span>)}
          {!many && pr?.stack && <span title="posición en el stack (1 = la de abajo)">◫ {pr.stack.position}/{pr.stack.size}</span>}
          {session.prState === "stale" && <span className="text-sky-400"
            title="El PR tiene commits nuevos desde tu revisión. El IDE mueve solo la sesión al head nuevo cuando su claude no está trabajando; si sigue este aviso, tiene cambios sin commitear: abre la sesión y toca Refrescar">⟳ commits nuevos desde tu revisión</span>}
          {session.prState === "closed" && <span>PR cerrada</span>}
          {session.pollError && <span className="text-destructive"
            title={`${session.pollError} (último OK: ${session.lastOk ?? "nunca"})`}>⚠ no se pudo consultar el PR</span>}
          {session.attention === "trust" && <span className="text-destructive"
            title="Claude Code pide confirmar la carpeta: abre la terminal y acepta">⚠ confiar carpeta</span>}
          {/* el detalle de los worktrees está en el módulo Desarrollo */}
          {session.repos.some((r) => r.state === "missing") && <span className="text-destructive"
            title="Falta el worktree de algún repo: míralo en el módulo Desarrollo">⚠ falta un worktree</span>}
          {session.repos.some((r) => r.setup === "failed") && <span className="text-destructive"
            title="Falló el setup de algún repo: míralo en el módulo Desarrollo">✗ setup</span>}
        </CardMeta>
      </CardShell>
      <ConfirmArchiveDialog id={session.id} open={confirm} onClose={() => setConfirm(false)} />
    </QueueItem>
  );
}

/** Las PRs ya mergeadas de una card: un "✓ N" que las despliega o esconde (recordado por card). Por
 *  defecto escondidas si la card tiene PRs abiertas; si todas están mergeadas, a la vista. */
function MergedToggle({ id, merged, hasOpen }: { id: string; merged: GhPr[]; hasOpen: boolean }) {
  const [show, setShow] = usePersistentOpen(`merged.${id}`, !hasOpen);
  return (<>
    <button title={show ? `Esconder las ${merged.length} PRs mergeadas` : `Mostrar las ${merged.length} PRs mergeadas`}
      aria-expanded={show} onClick={(e) => { e.stopPropagation(); setShow(!show); }}
      className={cn("rounded border px-1 font-mono text-[10px] font-bold text-purple-300 hover:bg-purple-400/15",
        show ? "border-purple-400/60 bg-purple-400/10" : "border-dashed border-purple-400/50")}>
      ✓ {merged.length}</button>
    {show && merged.map((p) => <RefChip key={p.url} repo={p.repo} number={p.number} pr={p} />)}
  </>);
}
