// ui/src/modules/dev/DevPanel.tsx
import { useEffect, useState } from "react";
import { useCurrentDev } from "../../main/currentDev";
import { ReviewDecision } from "../../main/ReviewDecision";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { freshSession, prsReady, setDevState, type GhPr } from "../../transport/folderSessions";
import { Button } from "../../components/ui/button";
import { ago, BLOCKS, devStateOf, MANUAL_PHASES, STATE, type State } from "../sessions/devStates";
import { cn } from "../../lib/utils";
import { PrRow } from "../sessions/MyDevsSection";
import { RepoLine } from "../sessions/RepoLine";
import { useGithubReviews } from "../sessions/ReviewsSection";
import { byRepoStack } from "../sessions/desarrollos";
import { DevIndex, DevTitle, repoShort } from "../sessions/DevCard";

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mx-2.5 mb-1 mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">{children}</div>;
}

function StateButton({ st, on, faded, onClick, disabled, title }:
  { st: State; on: boolean; faded?: boolean; onClick: () => void; disabled: boolean; title: string }) {
  const [label, bg, text] = STATE[st];
  return <button disabled={disabled} onClick={onClick} title={title}
    className={cn("rounded border px-1.5 py-0.5 text-[11px]", bg, text,
      on ? (faded ? "border-dashed border-current" : "border-current font-semibold") : "border-transparent opacity-60 hover:opacity-100")}>
    {label}</button>;
}

/** Estado del desarrollo: la fase (a mano hasta "listo para revisión"; después la da GitHub) y un
 *  bloqueo opcional encima, con nota. Con "listo para revisión", sacar sus PRs de draft. */
function StateEditor({ devKey, prs }: { devKey: string; prs: GhPr[] }) {
  const states = useFolders((s) => s.tree.devStates);
  const { gh } = useGithubReviews();
  const cur = devStateOf(states, devKey, prs);
  const [note, setNote] = useState(cur.note ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { setNote(cur.note ?? ""); setMsg(null); }, [devKey, cur.block, cur.note]);
  const act = (what: string, p: Promise<unknown>, ok?: string) => {
    setBusy(what); setMsg(null);
    p.then(() => ok && setMsg(ok)).catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`)).finally(() => setBusy(null));
  };
  const set = (st: string | null, n: string | null = null) => act("state", setDevState(getWs(), devKey, st, n));
  const drafts = prs.filter((p) => p.draft && gh?.me && p.author === `@${gh.me}`);
  return (
    <div className="mx-2.5">
      <div className="mb-0.5 text-[10px] text-muted-foreground">Fase</div>
      <div className="flex flex-wrap gap-1">
        {MANUAL_PHASES.map((st) => <StateButton key={st} st={st} disabled={busy !== null}
          on={(cur.manual ?? (cur.inferred ? cur.phase : null)) === st} faded={cur.inferred || cur.github}
          title={cur.manual === st ? `Fase puesta: ${STATE[st][0]}` : `Pasar a "${STATE[st][0]}" (quita el bloqueo)`}
          onClick={() => set(st)} />)}
      </div>
      {cur.github && <p className="mt-1 text-[11px]">Según GitHub: <span className={STATE[cur.phase][2]}>{STATE[cur.phase][0]}</span></p>}
      {cur.inferred && <p className="mt-1 text-[10px] text-muted-foreground">Sin fase puesta: se deduce de sus PRs.</p>}
      {cur.outOfDraft && <p className="mt-1 text-[11px] text-amber-300">Está "{STATE[cur.manual!][0]}" pero una PR ya no está en draft.</p>}

      <div className="mb-0.5 mt-2.5 text-[10px] text-muted-foreground">Bloqueo</div>
      <div className="flex flex-wrap gap-1">
        {BLOCKS.map((st) => <StateButton key={st} st={st} disabled={busy !== null} on={cur.block === st}
          title={cur.block === st ? `Bloqueado: ${STATE[st][0]}` : `Bloquear: ${STATE[st][0]} (con la nota de abajo)`}
          onClick={() => set(st, note.trim() || null)} />)}
        {cur.block && <button disabled={busy !== null} onClick={() => set("unblock")}
          title={`Quitar el bloqueo (vuelve a "${STATE[cur.phase][0]}")`}
          className="rounded border border-border px-1.5 py-0.5 text-[11px] hover:bg-accent">destrabar</button>}
      </div>
      <div className="mt-1.5 flex gap-1">
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300}
          placeholder="nota: qué falta y de quién" aria-label="Nota del estado"
          onKeyDown={(e) => { if (e.key === "Enter" && cur.block) set(cur.block, note.trim() || null); }}
          className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 text-[11px] outline-none focus:border-primary" />
        <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" disabled={!cur.block || busy !== null}
          title="Guardar la nota del bloqueo (Enter)" onClick={() => cur.block && set(cur.block, note.trim() || null)}>Nota</Button>
      </div>
      {cur.since && !cur.inferred && <p className="mt-1 text-[10px] text-muted-foreground">
        {cur.block ? "bloqueado" : "en esta fase"} desde hace {ago(cur.since)}</p>}
      {!devKey.startsWith("s:") && (cur.manual || cur.block) && (
        <button disabled={busy !== null} onClick={() => set(null)} title="Borrar lo puesto (fase y bloqueo): vuelve a deducirse de sus PRs"
          className="mt-1 text-[10px] text-muted-foreground underline hover:text-foreground">borrar estado</button>)}
      {cur.manual === "ready-for-review" && !cur.github && drafts.length > 0 && (
        <Button size="sm" className="mt-2 h-6 px-2 text-[11px]" disabled={busy !== null}
          title={`Sacar de draft (gh pr ready): ${drafts.map((p) => `${p.repo}#${p.number}`).join(", ")}`}
          onClick={() => act("ready", prsReady(getWs(), drafts.map((p) => p.url)), "Mandadas a revisión (GitHub lo refleja en el próximo poll)")}>
          {busy === "ready" ? "Mandando…" : `Mandar a revisión (${drafts.length})`}</Button>)}
      {msg && <p role={msg.startsWith("⚠") ? "alert" : undefined}
        className={cn("mt-1 text-[11px]", msg.startsWith("⚠") ? "text-destructive" : "text-muted-foreground")}>{msg}</p>}
    </div>
  );
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
      <div className="mx-2.5 mt-2.5 flex items-start gap-1.5 text-sm">
        <span className="mt-0.5"><DevIndex devKey={dev.key} prs={dev.prs} /></span>
        <DevTitle devKey={dev.key} prs={dev.prs} pencil
          original={s?.title ?? dev.prs[0]?.title ?? s?.id ?? ""} />
      </div>
      {s && <div className="mx-2.5 font-mono text-[10px] text-muted-foreground">{s.id} · {s.kind}{s.status ? ` · ${s.status}` : ""}</div>}
      {error && <p role="alert" className="mx-2.5 mt-2 text-destructive">{error}</p>}

      {s?.kind !== "review" && s?.kind !== "main" && (<>
        <Label>Estado del desarrollo</Label>
        <StateEditor devKey={dev.key} prs={dev.prs} />
      </>)}

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

      {s?.kind === "review" && s.prUrl && <div className="mx-1.5"><ReviewDecision url={s.prUrl} /></div>}
      {s && <FreshConversation sid={s.id} />}

      {s && s.kind !== "review" && (<>
        <Label>Worktrees</Label>
        {s.repos.length === 0 && <p className="mx-2.5 text-muted-foreground">La sesión no tiene repos (`ide repo add`).</p>}
        <div className="pr-2.5">{s.repos.map((r) => <RepoLine key={r.name} session={s} repo={r} />)}</div>
      </>)}
    </div>
  );
}

/** Nueva conversación: misma sesión, contexto limpio (la anterior queda en su transcript). */
function FreshConversation({ sid }: { sid: string }) {
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <div className="mx-2.5 mt-3">
      {confirm ? (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="text-amber-300">¿Cerrar la conversación actual y empezar una nueva? (lee su SESSION.md)</span>
          <Button size="sm" className="h-6 px-2 text-[11px]" title="Sí: nueva conversación"
            onClick={() => { setConfirm(false); freshSession(getWs(), sid).then(() => setMsg("conversación nueva lanzada"))
              .catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`)); }}>Sí</Button>
          <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" title="No" onClick={() => setConfirm(false)}>No</Button>
        </div>
      ) : (
        <button title="Empezar una conversación nueva de claude en esta sesión (misma carpeta, worktrees y SESSION.md); la anterior queda guardada"
          onClick={() => { setMsg(null); setConfirm(true); }}
          className="rounded border border-border px-1.5 py-0.5 text-[11px] hover:bg-accent">Nueva conversación</button>)}
      {msg && <p className={cn("mt-1 text-[11px]", msg.startsWith("⚠") ? "text-destructive" : "text-muted-foreground")}>{msg}</p>}
    </div>
  );
}
