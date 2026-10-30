// ui/src/main/PrState.tsx
import { useState } from "react";
import { Plus, X } from "lucide-react";
import { getWs } from "../transport/wsClient";
import { prReviewers, prsReady, type GhPr, type GithubReviews } from "../transport/folderSessions";
import { CiMark } from "../modules/sessions/ReviewsSection";
import { PersonChip } from "../lib/people";
import { Button } from "../components/ui/button";
import { cn } from "../lib/utils";

/** Estado de la PR en GitHub (una palabra) a partir de draft / revisores / decisión. */
export function prState(pr: GhPr): [string, string] {
  if (pr.draft) return ["Draft", "bg-zinc-500/20 text-zinc-300"];
  if (pr.review === "changes") return ["Cambios pedidos", "bg-red-500/15 text-red-400"];
  if (pr.review === "approved") return ["Aprobada", "bg-emerald-500/15 text-emerald-300"];
  if (!pr.reviewers?.length) return ["Sin revisores", "bg-sky-500/10 text-sky-300"];
  return ["En revisión", "bg-amber-400/15 text-amber-300"];
}
const REV: Record<string, [string, string]> = {
  approved: ["aprobó", "text-emerald-400"], changes: ["pidió cambios", "text-red-400"], requested: ["pendiente", "text-amber-300"],
};

/** Cabecera de la PR en el resumen: su estado, el CI y los revisores (en tus PRs: pedir revisión /
 *  sacar a alguien, y mandar a revisión si está en draft). */
export function PrState({ pr, gh }: { pr: GhPr; gh: GithubReviews }) {
  const mine = !!gh.me && pr.author === `@${gh.me}`;
  const [label, cls] = prState(pr);
  const [picking, setPicking] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const act = (p: Promise<unknown>, ok: string) => {
    setBusy(true); setMsg(null);
    p.then(() => setMsg(ok)).catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`)).finally(() => setBusy(false));
  };
  const current = new Set((pr.reviewers ?? []).map((r) => r.login));
  const needle = q.trim().toLowerCase();
  const options = (gh.members ?? []).filter((m) => m.login !== gh.me && !current.has(m.login)
    && (!needle || m.login.toLowerCase().includes(needle) || (m.name ?? "").toLowerCase().includes(needle))).slice(0, 8);
  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("rounded px-2 py-0.5 text-xs font-semibold", cls)}>{label}</span>
        {pr.ci && <span className="flex items-center gap-1 text-xs text-muted-foreground">CI <CiMark pr={pr} /></span>}
        {mine && pr.draft && (
          <Button size="sm" variant="secondary" className="h-6 px-2 text-xs" disabled={busy}
            title="Sacarla de draft (gh pr ready): queda lista para que la revisen"
            onClick={() => act(prsReady(getWs(), [pr.url]), "Mandada a revisión (GitHub lo refleja en el próximo poll)")}>
            Mandar a revisión</Button>)}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Revisores</span>
        {!pr.reviewers?.length && <span className="text-xs text-muted-foreground">ninguno</span>}
        {(pr.reviewers ?? []).map((r) => {
          const [what, c] = REV[r.state] ?? [r.state, "text-muted-foreground"];
          return (
            <span key={r.login} className="inline-flex items-center gap-1">
              <PersonChip login={r.login} title={`${r.login}: ${what}`} />
              <span className={cn("text-[10px]", c)}>{what}</span>
              {mine && r.state === "requested" && (
                <button aria-label={`Sacar a ${r.login}`} title={`Sacar a ${r.login} de los revisores`} disabled={busy}
                  onClick={() => act(prReviewers(getWs(), pr.url, [], [r.login]), `${r.login} ya no revisa`)}
                  className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"><X size={10} /></button>)}
            </span>);
        })}
        {mine && (picking ? (
          <span className="relative">
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="buscar persona…"
              aria-label="Buscar revisor" onKeyDown={(e) => { if (e.key === "Escape") { setPicking(false); setQ(""); } }}
              className="w-44 rounded border border-primary bg-background px-1.5 py-0.5 text-xs outline-none" />
            <span className="absolute left-0 top-full z-20 mt-1 w-56 rounded-md border border-border bg-popover p-1 shadow">
              {options.length === 0 && <span className="block px-2 py-1 text-xs text-muted-foreground">sin resultados</span>}
              {options.map((m) => (
                <button key={m.login} disabled={busy} title={`Pedirle revisión a ${m.login}`}
                  onClick={() => { setPicking(false); setQ(""); act(prReviewers(getWs(), pr.url, [m.login]), `Revisión pedida a ${m.login}`); }}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-accent">
                  <span className="font-mono">{m.login}</span>{m.name && <span className="ml-1.5 text-muted-foreground">{m.name}</span>}
                </button>))}
            </span>
          </span>
        ) : (
          <button title="Pedirle revisión a alguien de la org" disabled={busy} onClick={() => setPicking(true)}
            className="inline-flex items-center gap-0.5 rounded border border-dashed border-border px-1.5 py-px text-[11px] text-muted-foreground hover:text-foreground">
            <Plus size={10} /> revisor</button>))}
      </div>
      {msg && <p role={msg.startsWith("⚠") ? "alert" : undefined}
        className={cn("text-xs", msg.startsWith("⚠") ? "text-destructive" : "text-muted-foreground")}>{msg}</p>}
    </div>
  );
}
