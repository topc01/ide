// ui/src/modules/sessions/ReviewVerdict.tsx
import { useEffect, useState } from "react";
import { Check, MessageSquareWarning, RotateCcw } from "lucide-react";
import { getWs } from "../../transport/wsClient";
import { prReviewers, reviewDraft, reviewSubmit, type GhPr } from "../../transport/folderSessions";
import { QueueItemAction } from "../../components/ai-elements/queue";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { repoShort } from "./DevCard";
import { cn } from "../../lib/utils";

type Event = "approve" | "request-changes";
const WORD: Record<Event, [string, string]> = {
  approve: ["Aprobar", "¿Aprobar la PR en GitHub con este comentario?"],
  "request-changes": ["Pedir cambios", "¿Pedir cambios en GitHub con este comentario?"],
};

/** Acciones de hover de una PR que te pidieron revisar: Aprobar / Pedir cambios. Abren una ventana con
 *  el comentario (precargado con el review de la sesión de revisión, editable) y piden confirmar antes
 *  de publicar (`gh pr review`). */
export function ReviewVerdictActions({ pr }: { pr: GhPr }) {
  const [open, setOpen] = useState<Event | null>(null);
  const action = (ev: Event, icon: React.ReactNode, title: string) => (
    <QueueItemAction aria-label={`${WORD[ev][0]} ${pr.repo}#${pr.number}`} title={title}
      onClick={(e) => { e.stopPropagation(); setOpen(ev); }}>{icon}</QueueItemAction>);
  return (<>
    {action("approve", <Check size={11} />, "Aprobar la PR en GitHub (con comentario, pide confirmar)")}
    {action("request-changes", <MessageSquareWarning size={11} />, "Pedir cambios en GitHub (con comentario, pide confirmar)")}
    {open && <VerdictDialog pr={pr} initial={open} onClose={() => setOpen(null)} />}
  </>);
}

function VerdictDialog({ pr, initial, onClose }: { pr: GhPr; initial: Event; onClose: () => void }) {
  const [event, setEvent] = useState<Event>(initial);
  const [body, setBody] = useState("");
  const [why, setWhy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    reviewDraft(getWs(), pr.url).then((d) => {
      setBody(d.body);
      setWhy(d.verdict ? `La sesión: ${d.verdict === "approve" ? "aprobar" : "pedir cambios"}${d.why ? ` — ${d.why}` : ""}` : null);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [pr.url]);
  const submit = () => {
    setBusy(true); setErr(null);
    reviewSubmit(getWs(), pr.url, event, body).then(onClose)
      .catch((e: any) => { setErr(e?.message ?? String(e)); setConfirm(false); }).finally(() => setBusy(false));
  };
  const missing = event === "request-changes" && !body.trim();
  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      {/* el portal propaga los clicks a la card (React): que no la seleccionen */}
      <DialogContent onClick={(e) => e.stopPropagation()} className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="text-sm">{repoShort(pr.repo)} #{pr.number} · {pr.title}</DialogTitle>
        </DialogHeader>
        <div className="flex rounded-md border border-border p-0.5 text-xs">
          {(["approve", "request-changes"] as Event[]).map((ev) => (
            <button key={ev} title={WORD[ev][0]} onClick={() => { setEvent(ev); setConfirm(false); }}
              className={cn("flex-1 rounded-sm px-2 py-1", event === ev ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}>
              {WORD[ev][0]}</button>))}
        </div>
        {why && <p className="whitespace-pre-wrap text-xs text-muted-foreground">{why}</p>}
        <textarea value={body} onChange={(e) => { setBody(e.target.value); setConfirm(false); }} spellCheck={false}
          placeholder={loading ? "cargando el review de la sesión…" : event === "request-changes"
            ? "Comentario (obligatorio para pedir cambios)" : "Comentario (opcional)"}
          aria-label="Comentario del review"
          className="min-h-40 w-full resize-y rounded-md border border-border bg-muted p-2 font-mono text-xs text-foreground outline-none focus:border-primary" />
        {err && <p role="alert" className="text-xs text-destructive">⚠ {err}</p>}
        <DialogFooter className="items-center gap-2">
          {confirm ? (<>
            <span className="mr-auto text-xs text-amber-300">{WORD[event][1]}</span>
            <Button size="sm" variant="ghost" title="No publicar" onClick={() => setConfirm(false)}>No</Button>
            <Button size="sm" disabled={busy} title="Sí, publicar en GitHub" onClick={submit}>{busy ? "Publicando…" : "Sí, publicar"}</Button>
          </>) : (<>
            <Button size="sm" variant="ghost" title="Cerrar sin publicar" onClick={onClose}>Cancelar</Button>
            <Button size="sm" disabled={missing || loading} title={missing ? "Escribe el comentario para pedir cambios" : `${WORD[event][0]} en GitHub`}
              onClick={() => setConfirm(true)}>{WORD[event][0]}…</Button>
          </>)}
        </DialogFooter>
      </DialogContent>
    </Dialog>);
}

/** Acción de hover de un desarrollo tuyo: volver a pedir review a quienes pidieron cambios (en cada
 *  una de sus PRs), con confirmación (`gh pr edit --add-reviewer`). */
export function RereviewAction({ prs }: { prs: GhPr[] }) {
  const targets = prs.map((p) => ({ pr: p, logins: (p.reviewers ?? []).filter((r) => r.state === "changes").map((r) => r.login) }))
    .filter((t) => t.logins.length);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!targets.length) return null;
  const who = [...new Set(targets.flatMap((t) => t.logins))].map((l) => `@${l}`).join(", ");
  const go = () => {
    setBusy(true); setErr(null);
    Promise.all(targets.map((t) => prReviewers(getWs(), t.pr.url, t.logins))).then(() => setOpen(false))
      .catch((e: any) => setErr(e?.message ?? String(e))).finally(() => setBusy(false));
  };
  return (<>
    <QueueItemAction aria-label="Pedir re-review" title={`Pedir re-review a quienes pidieron cambios (${who})`}
      onClick={(e) => { e.stopPropagation(); setOpen(true); }}><RotateCcw size={11} /></QueueItemAction>
    {open && (
      <Dialog open onOpenChange={(o) => { if (!o) setOpen(false); }}>
        <DialogContent onClick={(e) => e.stopPropagation()} className="max-w-md">
          <DialogHeader><DialogTitle className="text-sm">¿Pedir re-review en GitHub?</DialogTitle></DialogHeader>
          <ul className="space-y-0.5 text-xs">
            {targets.map((t) => <li key={t.pr.url}><span className="font-mono font-bold">{repoShort(t.pr.repo)} #{t.pr.number}</span>
              {" → "}{t.logins.map((l) => `@${l}`).join(", ")}</li>)}
          </ul>
          {err && <p role="alert" className="text-xs text-destructive">⚠ {err}</p>}
          <DialogFooter className="gap-2">
            <Button size="sm" variant="ghost" title="No" onClick={() => setOpen(false)}>No</Button>
            <Button size="sm" disabled={busy} title="Sí, pedir re-review" onClick={go}>{busy ? "Pidiendo…" : "Sí, pedir re-review"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>)}
  </>);
}
