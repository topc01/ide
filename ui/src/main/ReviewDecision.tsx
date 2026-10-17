// ui/src/main/ReviewDecision.tsx
import { useCallback, useEffect, useState } from "react";
import { getWs } from "../transport/wsClient";
import { reviewDraft, reviewSubmit } from "../transport/folderSessions";
import { useFolders } from "../state/folders";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

/** Tu decisión sobre una PR que revisas: el veredicto que sugiere la sesión de revisión, su review
 *  listo para publicar (editable) y los botones Aprobar / Pedir cambios (publican con `gh pr review`).
 *  La sesión nunca publica sola. */
export function ReviewDecision({ url }: { url: string }) {
  const tree = useFolders((s) => s.tree);       // se relee cuando la sesión actualiza su SESSION.md
  const [draft, setDraft] = useState<{ id: string | null; verdict: string | null; why: string; body: string } | null>(null);
  const [body, setBody] = useState("");
  const [edited, setEdited] = useState(false);
  const [confirm, setConfirm] = useState<"approve" | "request-changes" | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => {
    reviewDraft(getWs(), url).then((d) => { setDraft(d); if (!edited) setBody(d.body); }).catch(() => setDraft(null));
  }, [url, edited]);
  useEffect(load, [load, tree]);
  const session = tree.sessions.find((s) => s.id === draft?.id);
  const submit = (event: "approve" | "request-changes") => {
    setConfirm(null); setBusy(true); setMsg(null);
    reviewSubmit(getWs(), url, event, body)
      .then(() => setMsg(event === "approve" ? "Aprobada en GitHub" : "Pediste cambios en GitHub"))
      .catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`)).finally(() => setBusy(false));
  };
  const verdict = draft?.verdict === "approve" ? ["Sugiere aprobar", "text-emerald-400"]
    : draft?.verdict === "request-changes" ? ["Sugiere pedir cambios", "text-amber-300"] : null;
  const done = session?.status === "approved" || session?.status === "changes-requested";
  return (
    <div className="mt-5 rounded-md border border-border p-3">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Tu revisión</span>
        {verdict ? <span className={cn("text-xs font-semibold", verdict[1])}>{verdict[0]}</span>
          : <span className="text-xs text-muted-foreground">{draft?.id ? "la sesión todavía no deja veredicto" : "sin sesión de revisión"}</span>}
        {done && <span className="text-xs text-muted-foreground">· estado: {session!.status === "approved" ? "aprobada" : "cambios pedidos"}</span>}
      </div>
      {draft?.why && <p className="mb-2 whitespace-pre-wrap text-xs text-muted-foreground">{draft.why}</p>}
      <textarea value={body} onChange={(e) => { setBody(e.target.value); setEdited(true); }} spellCheck={false}
        placeholder="Comentario del review (obligatorio para pedir cambios)" aria-label="Comentario del review"
        className="min-h-24 w-full resize-y rounded-md border border-border bg-muted p-2 font-mono text-xs text-foreground outline-none [field-sizing:content] focus:border-primary" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {confirm ? (<>
          <span className="text-xs text-amber-300">
            {confirm === "approve" ? "¿Aprobar la PR en GitHub con este comentario?" : "¿Pedir cambios en GitHub con este comentario?"}</span>
          <Button size="sm" disabled={busy} title="Sí, publicar" onClick={() => submit(confirm)}>Sí, publicar</Button>
          <Button size="sm" variant="ghost" title="No" onClick={() => setConfirm(null)}>No</Button>
        </>) : (<>
          <Button size="sm" disabled={busy} title="Aprobar la PR en GitHub (gh pr review --approve)" onClick={() => setConfirm("approve")}
            className={cn(draft?.verdict === "approve" && "ring-1 ring-emerald-400")}>Aprobar</Button>
          <Button size="sm" variant="secondary" disabled={busy || !body.trim()}
            title={body.trim() ? "Pedir cambios en GitHub (gh pr review --request-changes)" : "Escribe el comentario para pedir cambios"}
            onClick={() => setConfirm("request-changes")}
            className={cn(draft?.verdict === "request-changes" && "ring-1 ring-amber-300")}>Pedir cambios</Button>
          {edited && <button title="Volver al review que dejó la sesión" onClick={() => { setEdited(false); setBody(draft?.body ?? ""); }}
            className="text-[11px] text-muted-foreground underline hover:text-foreground">restaurar el de la sesión</button>}
        </>)}
        {busy && <span className="text-xs text-muted-foreground">publicando…</span>}
      </div>
      {msg && <p role={msg.startsWith("⚠") ? "alert" : undefined}
        className={cn("mt-1 text-xs", msg.startsWith("⚠") ? "text-destructive" : "text-muted-foreground")}>{msg}</p>}
    </div>
  );
}
