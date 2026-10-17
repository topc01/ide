// ui/src/modules/dev/DevPanel.tsx
import { useEffect, useState } from "react";
import { useCurrentDev } from "../../main/currentDev";
import { useFolders } from "../../state/folders";
import { getWs } from "../../transport/wsClient";
import { prsReady, setDevState } from "../../transport/folderSessions";
import { Button } from "../../components/ui/button";
import { ago, BLOCKED, DEV_STATE, DEV_STATE_ORDER, devStateOf, outOfDraft, type DevState } from "../sessions/devStates";
import { cn } from "../../lib/utils";
import { PrRow } from "../sessions/MyDevsSection";
import { RepoLine } from "../sessions/RepoLine";
import { useGithubReviews } from "../sessions/ReviewsSection";
import { byRepoStack } from "../sessions/desarrollos";
import { DevIndex, DevTitle, repoShort } from "../sessions/DevCard";

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mx-2.5 mb-1 mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">{children}</div>;
}

/** Estado del desarrollo: elegirlo (con nota, sobre todo en los bloqueos) y, cuando está listo para
 *  revisión, sacar sus PRs de draft. */
function StateEditor({ devKey, prs }: { devKey: string; prs: import("../../transport/folderSessions").GhPr[] }) {
  const states = useFolders((s) => s.tree.devStates);
  const { gh } = useGithubReviews();
  const cur = devStateOf(states, devKey, prs);
  const [note, setNote] = useState(cur?.inferred ? "" : cur?.note ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { setNote(cur?.inferred ? "" : cur?.note ?? ""); setMsg(null); }, [devKey, cur?.status, cur?.note, cur?.inferred]);
  const act = (what: string, p: Promise<unknown>, ok?: string) => {
    setBusy(what); setMsg(null);
    p.then(() => ok && setMsg(ok)).catch((e: any) => setMsg(`⚠ ${e?.message ?? String(e)}`)).finally(() => setBusy(null));
  };
  const pick = (st: DevState) => act("state", setDevState(getWs(), devKey, st, BLOCKED.includes(st) ? note.trim() || null : null));
  const drafts = prs.filter((p) => p.draft && gh?.me && p.author === `@${gh.me}`);
  return (
    <div className="mx-2.5">
      <div className="flex flex-wrap gap-1">
        {DEV_STATE_ORDER.map((st) => {
          const [label, bg, text] = DEV_STATE[st];
          const on = cur?.status === st;
          return <button key={st} disabled={busy !== null} onClick={() => pick(st)}
            title={on ? `${label}${cur?.inferred ? " (inferido de sus PRs)" : ""}` : `Pasar a "${label}"`}
            className={cn("rounded border px-1.5 py-0.5 text-[11px]", bg, text,
              on ? (cur?.inferred ? "border-dashed border-current" : "border-current font-semibold") : "border-transparent opacity-70 hover:opacity-100")}>
            {label}</button>;
        })}
        {!devKey.startsWith("s:") && cur && !cur.inferred && (
          <button disabled={busy !== null} onClick={() => act("state", setDevState(getWs(), devKey, null, null))}
            title="Quitar el estado puesto (vuelve al inferido de sus PRs)"
            className="rounded border border-dashed border-border px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground">
            sin estado</button>)}
      </div>
      <div className="mt-1.5 flex gap-1">
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300}
          placeholder="nota: qué falta y de quién (p.ej. cliente confirma formato)" aria-label="Nota del estado"
          onKeyDown={(e) => { if (e.key === "Enter" && cur && !cur.inferred) act("note", setDevState(getWs(), devKey, cur.status, note.trim() || null)); }}
          className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 text-[11px] outline-none focus:border-primary" />
        <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" disabled={!cur || cur.inferred || busy !== null}
          title="Guardar la nota en el estado actual (Enter)"
          onClick={() => cur && act("note", setDevState(getWs(), devKey, cur.status, note.trim() || null))}>Nota</Button>
      </div>
      {cur && !cur.inferred && cur.since && <p className="mt-1 text-[10px] text-muted-foreground">desde hace {ago(cur.since)}</p>}
      {cur?.inferred && <p className="mt-1 text-[10px] text-muted-foreground">Sin estado puesto: se infiere de sus PRs (draft = desarrollando).</p>}
      {outOfDraft(cur, prs) && <p className="mt-1 text-[11px] text-amber-300">El desarrollo sigue activo pero una PR ya no está en draft.</p>}
      {cur?.status === "ready-for-review" && drafts.length > 0 && (
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

      {s && s.kind !== "review" && (<>
        <Label>Worktrees</Label>
        {s.repos.length === 0 && <p className="mx-2.5 text-muted-foreground">La sesión no tiene repos (`ide repo add`).</p>}
        <div className="pr-2.5">{s.repos.map((r) => <RepoLine key={r.name} session={s} repo={r} />)}</div>
      </>)}
    </div>
  );
}
