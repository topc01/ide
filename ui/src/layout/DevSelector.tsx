// ui/src/layout/DevSelector.tsx
import { useEffect, useRef, useState } from "react";
import { ChevronDown, GitPullRequest, Search } from "lucide-react";
import { useFolders } from "../state/folders";
import { useStore } from "../state/store";
import type { FolderSession, GhPr, GithubReviews } from "../transport/folderSessions";
import { CiMark, DepsBadge, StackBadge, useGithubReviews } from "../modules/sessions/ReviewsSection";
import { cn } from "../lib/utils";

/** Un desarrollo = una sesión o una PR (sin sesión) de las listas de la sidebar. */
export type Desarrollo =
  | { kind: "session"; key: string; session: FolderSession; pr?: GhPr; group: string }
  | { kind: "pr"; key: string; pr: GhPr; group: string };

export function desarrollos(sessions: FolderSession[], gh: GithubReviews | null): Desarrollo[] {
  const prs = new Map<string, GhPr>();
  const groupOf = new Map<string, string>();
  const add = (list: GhPr[] | undefined, group: string) => (list ?? []).forEach((p) => {
    if (!prs.has(p.url)) { prs.set(p.url, p); groupOf.set(p.url, group); }
  });
  add(gh?.pending, "Revisiones"); add(gh?.changesRequested, "Revisiones");
  Object.values(gh?.mine ?? {}).forEach((l) => add(l, "Mis PRs"));
  const bySession = new Map([...prs.values()].map((p) => [p.sessionId, p]));
  const out: Desarrollo[] = sessions.map((s) => ({
    kind: "session", key: `s:${s.id}`, session: s, pr: bySession.get(s.id),
    group: s.kind === "review" ? "Revisiones" : "Sesiones",
  }));
  const withSession = new Set(sessions.map((s) => s.id));
  for (const p of prs.values()) {
    if (!withSession.has(p.sessionId)) out.push({ kind: "pr", key: `p:${p.url}`, pr: p, group: groupOf.get(p.url)! });
  }
  return out;
}

const GROUPS = ["Sesiones", "Revisiones", "Mis PRs"];
const titleOf = (d: Desarrollo) => d.kind === "session" ? d.session.title ?? d.session.id : d.pr.title;

function DevLine({ d }: { d: Desarrollo }) {
  const pr = d.kind === "session" ? d.pr : d.pr;
  return (
    <div className="min-w-0 flex-1 text-left">
      <div className="flex items-center gap-1.5">
        {d.kind === "session"
          ? <span className={cn(d.session.process === "running" ? "text-primary" : "text-muted-foreground")}>
              {d.session.process === "running" ? "●" : "○"}</span>
          : <GitPullRequest size={11} className="shrink-0 text-muted-foreground" />}
        <span className="truncate text-xs" title={titleOf(d)}>{titleOf(d)}</span>
        {pr && <CiMark pr={pr} />}
      </div>
      <div className="flex items-center gap-1.5 pl-4 font-mono text-[10px] text-muted-foreground">
        <span className="truncate">{d.kind === "session" ? d.session.id : `${d.pr.repo}#${d.pr.number}`}</span>
        {pr && <StackBadge pr={pr} />}
        {pr && <DepsBadge pr={pr} />}
      </div>
    </div>
  );
}

/** Selector del desarrollo actual (arriba del menú de acciones + sidebar interna). */
export function DevSelector() {
  const { tree, activeId, activePrUrl, setActive, setActivePr } = useFolders();
  const innerOpen = useStore((s) => s.innerSidebarOpen);
  const { gh } = useGithubReviews();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const all = desarrollos(tree.sessions, gh);
  const current = all.find((d) => activePrUrl ? d.kind === "pr" && d.pr.url === activePrUrl
    : d.kind === "session" && d.session.id === activeId);
  const needle = q.trim().toLowerCase();
  const shown = all.filter((d) => !needle || `${titleOf(d)} ${d.kind === "session" ? d.session.id
    : `${d.pr.repo}#${d.pr.number}`}`.toLowerCase().includes(needle));
  const pick = (d: Desarrollo) => {
    if (d.kind === "session") setActive(d.session.id); else setActivePr(d.pr.url);
    setOpen(false); setQ("");
  };

  return (
    <div ref={ref} className={cn("relative shrink-0 border-b border-r border-border bg-card", innerOpen ? "w-[300px]" : "w-11")}>
      <button aria-label="Cambiar de desarrollo" title="Cambiar de desarrollo" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-2 hover:bg-accent/60">
        {innerOpen ? (<>
          {current ? <DevLine d={current} />
            : <span className="flex-1 text-left text-xs text-muted-foreground">Elige un desarrollo…</span>}
          <ChevronDown size={13} className={cn("shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
        </>) : <ChevronDown size={14} className="mx-auto text-muted-foreground" />}
      </button>
      {open && (
        <div role="listbox" className="absolute left-0 top-full z-30 flex max-h-[70vh] w-[300px] flex-col rounded-b-md border border-border bg-popover shadow-lg">
          <label className="flex items-center gap-1.5 border-b border-border px-2.5 py-1.5">
            <Search size={12} className="text-muted-foreground" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar desarrollo…"
              className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground" />
          </label>
          <div className="overflow-auto py-1">
            {GROUPS.map((g) => {
              const items = shown.filter((d) => d.group === g);
              if (items.length === 0) return null;
              return (
                <div key={g}>
                  <div className="px-2.5 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">{g}</div>
                  {items.map((d) => (
                    <button title="Cambiar a este desarrollo" key={d.key} role="option" aria-selected={d.key === current?.key} onClick={() => pick(d)}
                      className={cn("flex w-full border-l-2 border-transparent px-2.5 py-1 hover:bg-accent",
                        d.key === current?.key && "border-primary bg-accent")}>
                      <DevLine d={d} />
                    </button>))}
                </div>);
            })}
            {shown.length === 0 && <p className="px-2.5 py-2 text-xs text-muted-foreground">Sin resultados.</p>}
          </div>
        </div>)}
    </div>
  );
}
