// ui/src/layout/DevSelector.tsx
import { useEffect, useRef, useState } from "react";
import { ChevronDown, GitPullRequest, Search } from "lucide-react";
import { useFolders } from "../state/folders";
import { useStore } from "../state/store";
import type { FolderSession, GhPr, GithubReviews, PrLinks } from "../transport/folderSessions";
import { CiMark, DepsBadge, StackBadge, allPrs, useGithubReviews } from "../modules/sessions/ReviewsSection";
import { deriveMine, devIndexOf, devName, worstPr } from "../modules/sessions/desarrollos";
import { DevIndex, RepoChips } from "../modules/sessions/DevCard";
import { cn } from "../lib/utils";

/** Un desarrollo = una sesión o una PR (sin sesión) de las listas de la sidebar. */
export type Desarrollo =
  | { kind: "session"; key: string; session: FolderSession; pr?: GhPr; prs: GhPr[]; group: string }
  | { kind: "pr"; key: string; pr: GhPr; group: string };

export function desarrollos(sessions: FolderSession[], gh: GithubReviews | null, links?: PrLinks): Desarrollo[] {
  const prs = new Map<string, GhPr>();
  const groupOf = new Map<string, string>();
  const add = (list: GhPr[] | undefined, group: string) => (list ?? []).forEach((p) => {
    if (!prs.has(p.url)) { prs.set(p.url, p); groupOf.set(p.url, group); }
  });
  add(gh?.pending, "Revisiones"); add(gh?.changesRequested, "Revisiones");
  Object.values(gh?.mine ?? {}).forEach((l) => add(l, "Mis desarrollos"));
  // las PRs de cada sesión: las de las ramas de sus worktrees (puede ser fullstack) o la revisada
  const mine = deriveMine(sessions.filter((s) => s.kind !== "review"), gh, links);
  const every = gh ? allPrs(gh) : [];
  const out: Desarrollo[] = sessions.map((s) => {
    const sprs = s.kind === "review" ? every.filter((p) => p.sessionId === s.id)
      : mine.find((d) => d.session?.id === s.id)?.prs ?? [];
    return { kind: "session", key: `s:${s.id}`, session: s, prs: sprs, pr: worstPr(sprs).ci ?? sprs[0],
             group: s.kind === "review" ? "Revisiones" : "Sesiones" };
  });
  const withSession = new Set(sessions.map((s) => s.id));
  for (const p of prs.values()) {
    if (!withSession.has(p.sessionId)) out.push({ kind: "pr", key: `p:${p.url}`, pr: p, group: groupOf.get(p.url)! });
  }
  return out;
}

const GROUPS = ["Sesiones", "Mis desarrollos", "Revisiones"];
const original = (d: Desarrollo) => d.kind === "session"
  ? (d.session.kind === "main" ? "Manager" : d.session.title ?? d.session.id) : d.pr.title;
const prsOf = (d: Desarrollo) => d.kind === "session" ? d.prs : [d.pr];

function DevLine({ d, names }: { d: Desarrollo; names?: Record<string, string> }) {
  const pr = d.kind === "session" ? d.pr : d.pr;
  const name = devName(names, d.key, prsOf(d));
  const title = name ?? original(d);
  const repos = d.kind === "session"
    ? [...new Set([...d.session.repos.map((r) => r.name), ...d.prs.map((p) => p.repo)])].sort() : [];
  return (
    <div className="min-w-0 flex-1 text-left">
      <div className="flex items-center gap-1.5">
        {d.kind === "session"
          ? <span className={cn(d.session.process === "running" ? "text-primary" : "text-muted-foreground")}>
              {d.session.process === "running" ? "●" : "○"}</span>
          : <GitPullRequest size={11} className="shrink-0 text-muted-foreground" />}
        <DevIndex devKey={d.key} prs={prsOf(d)} />
        <span className="truncate text-xs" title={name ? `${name}\n(original: ${original(d)})` : title}>{title}</span>
        {pr && <CiMark pr={pr} />}
      </div>
      <div className="flex items-center gap-1.5 pl-4 font-mono text-[10px] text-muted-foreground">
        <span className="truncate">{d.kind === "session" ? (d.session.kind === "main" ? "sesión principal" : d.session.id) : `${d.pr.repo}#${d.pr.number}`}</span>
        {repos.length > 1 && <RepoChips repos={repos} />}
        {pr && (d.kind === "pr" || d.prs.length === 1) && <StackBadge pr={pr} />}
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

  const all = desarrollos(tree.sessions, gh, tree.devPrs);
  const names = tree.devNames;
  const current = all.find((d) => activePrUrl ? d.kind === "pr" && d.pr.url === activePrUrl
    : d.kind === "session" && d.session.id === activeId);
  const needle = q.trim().toLowerCase();
  const shown = all.filter((d) => !needle || `#${devIndexOf(tree.devIndex, d.key, prsOf(d)) ?? ""} ${devName(names, d.key, prsOf(d)) ?? ""} ${original(d)} ${d.kind === "session" ? d.session.id
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
          {current ? <DevLine d={current} names={names} />
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
                      <DevLine d={d} names={names} />
                    </button>))}
                </div>);
            })}
            {shown.length === 0 && <p className="px-2.5 py-2 text-xs text-muted-foreground">Sin resultados.</p>}
          </div>
        </div>)}
    </div>
  );
}
