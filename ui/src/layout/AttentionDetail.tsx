// ui/src/layout/AttentionDetail.tsx
/** Detalle al lado de la lista «te esperan» / «trabajando» de la barra inferior: por qué te espera la sesión
 *  (su último mensaje, el permiso que pide o su pregunta con opciones) o qué está haciendo, y responderle ahí. */
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchAttention, replyAttention, type Attention } from "../transport/folderSessions";
import { getWs } from "../transport/wsClient";
import { cn } from "../lib/utils";

const hhmm = (iso?: string | null) => iso ? new Date(iso).toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" }) : "";

const REASON: Record<string, string> = {
  turn: "terminó su turno", permission: "pide un permiso", idle: "lleva rato inactiva",
  interrupt: "la interrumpiste", launch: "recién abierta",
};

/** Las preguntas de su último mensaje (líneas que terminan en «?»). */
function questionsIn(text: string | null): string[] {
  return (text ?? "").split("\n").map((l) => l.replace(/^[\s>*\-•\d.)]+/, "").replace(/\*\*/g, "").trim())
    .filter((l) => l.endsWith("?") && l.length > 3).slice(-4);
}

export function AttentionDetail({ sid, title, mode, pinned, onGo }:
  { sid: string; title: string; mode: "waiting" | "working"; pinned: boolean; onGo: () => void }) {
  const [d, setD] = useState<Attention | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    setD(null); setErr(null); setText(""); setAnswers({}); setDone(null);
    const load = () => fetchAttention(getWs(), sid).then((x) => live && setD(x))
      .catch((e) => live && setErr(String(e?.message ?? e)));
    load();
    const t = window.setInterval(load, mode === "working" ? 3000 : 5000);
    return () => { live = false; window.clearInterval(t); };
  }, [sid, mode]);
  useEffect(() => { box.current?.scrollTo({ top: 0 }); }, [sid]);

  const send = async (action: "text" | "approve" | "deny" | "answer") => {
    if (!d || busy) return;
    setBusy(true); setErr(null);
    try {
      const r = await replyAttention(getWs(), { id: sid, action, text: text.trim() || undefined, answers,
        since: d.activity.since, pending: d.pending?.id ?? null });
      setDone(r.done); setText(""); setAnswers({});
      setD(await fetchAttention(getWs(), sid));
    } catch (e: any) {
      setErr(String(e?.message ?? e));
      fetchAttention(getWs(), sid).then(setD).catch(() => undefined);
    } finally { setBusy(false); }
  };

  const act = d?.activity ?? {};
  const pend = d?.pending ?? null;
  const asking = pend?.tool === "AskUserQuestion" && pend.questions?.length ? pend.questions : null;
  const permission = act.state === "waiting" && act.reason === "permission";
  const textQuestions = mode === "waiting" && !pend ? questionsIn(d?.message ?? null) : [];
  const isNum = /^\d+$/.test(sid);

  return (
    <div ref={box} className="flex max-h-[70vh] flex-col overflow-y-auto rounded-md border border-border bg-popover p-3 font-mono text-xs shadow-xl">
      <div className="mb-2 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-foreground">{isNum ? `#${sid} ` : ""}{title}</div>
          <div className="text-[11px] text-muted-foreground">
            {act.state === "working" ? `trabajando desde ${hhmm(act.since)}`
              : act.state === "waiting" ? `te espera desde ${hhmm(act.since)} · ${REASON[act.reason ?? ""] ?? "terminó"}`
                : "ya no te espera"}
            {!pinned && " · click en la lista para fijarlo"}
          </div>
        </div>
        <button title="Abrir esta sesión (o Enter en la lista)" onClick={onGo}
          className="shrink-0 rounded border border-border px-1.5 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground">ir a la sesión</button>
      </div>

      {!d && !err && <div className="text-muted-foreground">cargando…</div>}

      {permission && pend && (
        <div className="mb-2 rounded border border-orange-400/60 bg-orange-400/10 p-2">
          <div className="mb-1 font-semibold text-orange-300">Pide permiso para:</div>
          {pend.description && <div className="mb-1 text-foreground">{pend.description}</div>}
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-background/60 p-1.5 text-[11px]">
            {pend.command ?? pend.summary}</pre>
          <div className="mt-2 flex gap-2">
            <button disabled={busy} onClick={() => send("approve")} title="Autorizar esta vez (igual que «Yes» en su terminal)"
              className="rounded border border-emerald-500/70 px-2 py-0.5 text-emerald-300 hover:bg-emerald-500/15 disabled:opacity-50">✓ Autorizar</button>
            <button disabled={busy} onClick={() => send("deny")} title="Rechazar; si escribiste algo abajo, se lo dice como lo que tiene que hacer en vez de eso"
              className="rounded border border-destructive/70 px-2 py-0.5 text-destructive hover:bg-destructive/10 disabled:opacity-50">✕ Rechazar</button>
          </div>
        </div>
      )}
      {permission && !pend && act.note && (
        <div className="mb-2 rounded border border-orange-400/60 bg-orange-400/10 p-2 text-orange-200">
          {act.note}<div className="mt-1 text-[11px] text-muted-foreground">No veo qué pide exactamente: respóndelo en su terminal.</div></div>
      )}

      {asking && act.state === "waiting" && (
        <div className="mb-2 rounded border border-orange-400/60 bg-orange-400/10 p-2">
          <div className="mb-1 font-semibold text-orange-300">Te pregunta:</div>
          {asking.map((q, i) => (
            <div key={i} className="mb-2">
              <div className="mb-1 text-foreground">{q.question}</div>
              <div className="flex flex-col gap-1">
                {q.options.map((o, j) => {
                  const cur = (answers[String(i)] ?? "").split(" + ").filter(Boolean);
                  const on = cur.includes(o.label ?? "");
                  const pick = () => setAnswers((a) => ({ ...a, [String(i)]: q.multiSelect
                    ? (on ? cur.filter((x) => x !== o.label) : [...cur, o.label ?? ""]).join(" + ") : (o.label ?? "") }));
                  return (
                    <button key={j} onClick={pick} title={o.description ?? o.label ?? ""}
                      className={cn("rounded border px-2 py-1 text-left", on ? "border-primary bg-primary/15 text-foreground" : "border-border text-muted-foreground hover:bg-accent")}>
                      <span className="font-semibold">{o.label}</span>
                      {o.description && <span className="block text-[11px] text-muted-foreground">{o.description}</span>}
                    </button>);
                })}
              </div>
            </div>))}
          <button disabled={busy || !Object.keys(answers).length} onClick={() => send("answer")}
            title="Mandarle las opciones elegidas (y lo que escribas abajo)"
            className="rounded border border-emerald-500/70 px-2 py-0.5 text-emerald-300 hover:bg-emerald-500/15 disabled:opacity-50">Responder</button>
        </div>
      )}

      {textQuestions.length > 0 && (
        <div className="mb-2 rounded border border-orange-400/60 bg-orange-400/10 p-2">
          <div className="mb-1 font-semibold text-orange-300">Te pregunta:</div>
          {textQuestions.map((q, i) => <div key={i} className="text-foreground">{q}</div>)}
        </div>
      )}

      {d?.message && (
        <div className="mb-2">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            {mode === "working" ? "su último mensaje" : "su mensaje"} · {hhmm(d.messageAt)}</div>
          <div className="md max-h-[36vh] overflow-y-auto text-[12px]"><ReactMarkdown remarkPlugins={[remarkGfm]}>{d.message}</ReactMarkdown></div>
        </div>
      )}

      {mode === "working" && d && d.recent.length > 0 && (
        <div className="mb-2">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">lo último que hizo</div>
          {d.recent.map((r, i) => (
            <div key={i} className={cn("flex gap-2", i === 0 ? "text-foreground" : "text-muted-foreground")}>
              <span className="shrink-0 text-[10px]">{hhmm(r.at)}</span>
              <span className="min-w-0 truncate" title={r.summary}>{r.summary}</span>
            </div>))}
        </div>
      )}

      <div className="mt-auto border-t border-border pt-2">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
          placeholder={permission ? "Escribe para rechazar y decirle qué hacer en vez de eso…"
            : mode === "working" ? "Escríbele (le llega cuando termine lo que está haciendo)…" : "Respóndele…"}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (text.trim()) send(permission ? "deny" : "text"); }
            else if (e.key === "Escape") { e.preventDefault(); (e.target as HTMLTextAreaElement).blur(); }
            e.stopPropagation();
          }}
          className="w-full resize-y rounded border border-border bg-background p-1.5 text-[12px] text-foreground outline-none focus:border-primary" />
        <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
          <span className="flex-1">Enter envía · Shift+Enter, otra línea · Esc sale del campo</span>
          <button disabled={busy || !text.trim()} onClick={() => send(permission ? "deny" : "text")}
            title={permission ? "Rechazar el permiso y mandarle esto" : "Mandarle este mensaje a su terminal"}
            className="rounded border border-primary/60 px-2 py-0.5 text-primary hover:bg-primary/10 disabled:opacity-50">Enviar</button>
        </div>
        {done && <div className="mt-1 text-emerald-300">✓ {done}</div>}
        {err && <div className="mt-1 text-destructive">{err}</div>}
      </div>
    </div>
  );
}
