// ui/src/modules/review/ReviewPanel.tsx
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, ExternalLink, RefreshCw } from "lucide-react";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { fetchDiscussion, type Discussion, type GhPr } from "../../transport/folderSessions";
import { CiMark, DepsList, ReviewerChips, useGithubReviews } from "../sessions/ReviewsSection";
import { desarrolloPrs } from "../github/GithubPanel";
import { cn } from "../../lib/utils";

const REFRESH_MS = 60_000;
const DECISION: Record<string, [string, string]> = {
  APPROVED: ["aprobada", "text-emerald-400"], CHANGES_REQUESTED: ["cambios pedidos", "text-amber-300"],
  REVIEW_REQUIRED: ["falta review", "text-sky-400"],
};
const REVIEW_STATE: Record<string, [string, string]> = {
  APPROVED: ["aprobó", "text-emerald-400"], CHANGES_REQUESTED: ["pidió cambios", "text-amber-300"],
  COMMENTED: ["comentó", "text-muted-foreground"], DISMISSED: ["descartada", "text-muted-foreground"],
};

/** Texto de un comentario sin HTML ni imágenes (los bots meten comentarios y badges). */
function clean(body: string): string {
  return body.replace(/<!--[\s\S]*?-->/g, "").replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/<[^>]+>/g, "").replace(/\n{3,}/g, "\n\n").trim();
}
const when = (iso: string | null) => iso ? new Date(iso).toLocaleString("es", { dateStyle: "short", timeStyle: "short" }) : "";

function Body({ text }: { text: string }) {
  const [more, setMore] = useState(false);
  const t = clean(text);
  if (!t) return null;
  const long = t.length > 280 || t.split("\n").length > 6;
  return (
    <div className="mt-0.5">
      <p className={cn("whitespace-pre-wrap break-words text-[11px] leading-snug", !more && long && "line-clamp-6")}>{t}</p>
      {long && <button title={more ? "Mostrar menos" : "Mostrar el comentario completo"}
        onClick={() => setMore((m) => !m)} className="text-[10px] text-primary hover:underline">
        {more ? "ver menos" : "ver más"}</button>}
    </div>
  );
}

function OpenLink({ url, label }: { url: string | null; label: string }) {
  if (!url) return null;
  return <a href={url} target="_blank" rel="noreferrer" title={label} aria-label={label}
    className="ml-auto shrink-0 text-muted-foreground opacity-0 hover:text-foreground group-hover/c:opacity-100">
    <ExternalLink size={11} /></a>;
}

function Section({ title, count, open: initial = true, children }:
  { title: string; count: number; open?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className="mt-2">
      <button title="Colapsar / expandir" onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 px-2.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
        <ChevronRight size={11} className={cn("transition-transform", open && "rotate-90")} />{title}
        <span className="ml-auto font-mono text-primary">{count}</span>
      </button>
      {open && children}
    </div>
  );
}

function PrDiscussion({ pr }: { pr: GhPr }) {
  const [d, setD] = useState<Discussion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    setBusy(true);
    fetchDiscussion(getWs(), pr.url).then((x) => { setD(x); setError(null); })
      .catch((e: any) => setError(e?.message ?? String(e))).finally(() => setBusy(false));
  }, [pr.url]);
  useEffect(() => { load(); const t = setInterval(load, REFRESH_MS); return () => clearInterval(t); }, [load]);

  const open = d?.threads.filter((t) => !t.resolved) ?? [];
  const resolved = d?.threads.filter((t) => t.resolved) ?? [];
  const failed = d?.checks.filter((c) => c.state === "failure") ?? [];
  const [decision, decisionCls] = DECISION[d?.decision ?? ""] ?? ["sin review", "text-muted-foreground"];
  return (
    <div className="mb-3 border-b border-border pb-2">
      <div className="flex items-start gap-1.5 px-2.5">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold" title={pr.title}>{pr.title}</div>
          <div className="truncate font-mono text-[10px] text-muted-foreground">{pr.repo}#{pr.number} · {pr.head} → {pr.base}</div>
        </div>
        <button title="Actualizar desde GitHub" aria-label="Actualizar" onClick={load} disabled={busy}
          className="text-muted-foreground hover:text-foreground disabled:opacity-50">
          <RefreshCw size={11} className={cn(busy && "animate-spin")} /></button>
        <a href={pr.url} target="_blank" rel="noreferrer" title="Abrir en GitHub" aria-label="Abrir en GitHub"
          className="text-muted-foreground hover:text-foreground"><ExternalLink size={11} /></a>
      </div>
      {error && <p role="alert" className="mx-2.5 mt-1 text-xs text-destructive">{error}</p>}
      {!d && !error && <p className="mx-2.5 mt-1 text-xs text-muted-foreground">cargando…</p>}
      {d && (<>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 px-2.5 text-[11px]">
          {d.state !== "OPEN" && <span className="text-muted-foreground">{d.state === "MERGED" ? "mergeada" : "cerrada"}</span>}
          {d.draft && <span className="text-muted-foreground">draft</span>}
          <span className={decisionCls}>{decision}</span>
          <span className="flex items-center gap-1">CI <CiMark pr={{ ...pr, ci: d.ci, conflict: d.conflict }} /></span>
          {d.conflict && <span className="text-red-500">conflicto con {d.base}</span>}
        </div>
        <ReviewerChips pr={{ ...pr, reviewers: d.reviewers as GhPr["reviewers"] }} />
        {failed.length > 0 && (
          <ul className="mt-1 px-2.5">
            {failed.map((c) => (
              <li key={c.name} className="group/c flex items-center gap-1 text-[11px] text-red-500">
                <span className="truncate" title={c.name ?? ""}>✗ {c.name}</span>
                <OpenLink url={c.url} label="Ver el log del check" />
              </li>))}
          </ul>)}
        {!!pr.deps?.length && (
          <Section title="Dependencias" count={pr.depsPending ?? 0}>
            <div className="px-2.5"><DepsList pr={pr} /></div>
          </Section>)}
        <Section title="Hilos abiertos" count={open.length}>
          {open.length === 0 && <p className="px-2.5 text-[11px] text-muted-foreground">Sin hilos abiertos.</p>}
          {open.map((t, i) => <Thread key={i} t={t} />)}
        </Section>
        {resolved.length > 0 && (
          <Section title="Hilos resueltos" count={resolved.length} open={false}>
            {resolved.map((t, i) => <Thread key={i} t={t} />)}
          </Section>)}
        <Section title="Conversación" count={d.conversation.length}>
          {d.conversation.map((c, i) => {
            const [label, cls] = c.state ? REVIEW_STATE[c.state] ?? [c.state, ""] : ["comentó", "text-muted-foreground"];
            return (
              <div key={i} className="group/c mx-1.5 mb-1 rounded px-1.5 py-1 hover:bg-accent/40">
                <div className="flex items-center gap-1.5 text-[10px]">
                  <span className="font-mono">{c.author}</span><span className={cls}>{label}</span>
                  <span className="text-muted-foreground">{when(c.at)}</span>
                  <OpenLink url={c.url} label="Abrir este comentario en GitHub" />
                </div>
                <Body text={c.body} />
              </div>);
          })}
        </Section>
      </>)}
    </div>
  );
}

function Thread({ t }: { t: Discussion["threads"][number] }) {
  return (
    <div className={cn("mx-1.5 mb-1 rounded border border-border px-1.5 py-1", t.resolved && "opacity-60")}>
      <div className="group/c flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
        <span className="truncate" title={`${t.path}:${t.line ?? "?"}`}>{t.path}:{t.line ?? "?"}</span>
        {t.outdated && <span title="El código cambió desde este comentario">· desactualizado</span>}
        <OpenLink url={t.comments[0]?.url ?? null} label="Abrir el hilo en GitHub" />
      </div>
      {t.comments.map((c, i) => (
        <div key={i} className={cn("mt-1", i > 0 && "border-l border-border pl-1.5")}>
          <div className="flex items-center gap-1.5 text-[10px]">
            <span className="font-mono">{c.author}</span><span className="text-muted-foreground">{when(c.at)}</span>
          </div>
          <Body text={c.body} />
        </div>))}
    </div>
  );
}

/** Módulo Revisión: estado, hilos y conversación de las PRs del desarrollo actual. */
export function ReviewPanel() {
  const { tree, activeId, activePrUrl } = useFolders();
  const session = tree.sessions.find((s) => s.id === activeId);
  const { gh, error } = useGithubReviews();
  const prs = gh ? desarrolloPrs(session, activePrUrl, gh) : [];
  return (
    <div className="flex w-full min-w-0 flex-col overflow-hidden">
      <div className="mx-2.5 mb-1 mt-2.5 text-[10px] uppercase tracking-wide text-muted-foreground">Revisión</div>
      {error && <p role="alert" className="mx-2.5 text-xs text-destructive">{error}</p>}
      {!session && !activePrUrl && <p className="mx-2.5 text-xs text-muted-foreground">Elige un desarrollo para ver su revisión.</p>}
      {(session || activePrUrl) && gh && prs.length === 0 && (
        <p className="mx-2.5 text-xs text-muted-foreground">Este desarrollo no tiene PRs abiertas.</p>)}
      {prs.map((pr) => <PrDiscussion key={pr.url} pr={pr} />)}
    </div>
  );
}
