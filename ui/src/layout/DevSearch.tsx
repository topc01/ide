// ui/src/layout/DevSearch.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { go, recentKeys, useSearch } from "./devShortcuts";
import { useFolders } from "../state/folders";
import { ACTIVITY, activityOf } from "../modules/sessions/activity";
import { cn } from "../lib/utils";
import { getWs } from "../transport/wsClient";
import { allPrs, useGithubReviews } from "../modules/sessions/ReviewsSection";
import { deriveMine } from "../modules/sessions/desarrollos";
import { repoShort } from "../modules/sessions/DevCard";

type Archived = { id: string; kind: string | null; n: number | null; title: string | null; archivedAt: string | null };

const norm = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Puntaje fuzzy de `q` en `text` (mayor = mejor; null = no calza). Texto seguido gana, y antes mejor; si
 *  no, las letras en orden (subsecuencia), con castigo por los saltos. Cada palabra de `q` tiene que calzar. */
export function fuzzy(q: string, text: string): number | null {
  const t = norm(text);
  let total = 0;
  for (const w of norm(q).split(/\s+/).filter(Boolean)) {
    const at = t.indexOf(w);
    if (at >= 0) { total += 1000 - at - (at > 0 && /\w/.test(t[at - 1]) ? 50 : 0); continue; }
    let i = 0, gaps = 0, last = -1;
    for (const c of w) {
      const j = t.indexOf(c, i);
      if (j < 0) return null;
      if (last >= 0) gaps += j - last - 1;
      last = j; i = j + 1;
    }
    total += 500 - gaps * 5 - (t.indexOf(w[0]));
  }
  return total;
}

type Item = { key: string; n: number | null; title: string; tag: string | null; dot: [string, string, string] | null; archived?: boolean;
  /** una PR: su etiqueta (`API #5280`) y el desarrollo que se abre (su sesión, o la card de la PR) */
  pr?: { label: string; number: number; go: string } };

/** ⌘K (como Spotlight): un input y abajo las sesiones que calzan, por número primero (`12`, `#12`) y
 *  después por nombre (fuzzy). ↑/↓ mueven, Enter abre, Esc o ⌘K otra vez cierran. Vacío: por último
 *  acceso. Al escribir, también las **archivadas** (al final, «Archivada»): Enter una vez pide confirmar,
 *  Enter otra vez la reabre (vuelven su carpeta, worktrees y rama; su claude se retoma) y la abre. */
export function DevSearch() {
  const open = useSearch((s) => s.open);
  const tree = useFolders((s) => s.tree);
  const [q, setQ] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const sel = useRef<HTMLButtonElement>(null);
  const [archived, setArchived] = useState<Archived[]>([]);
  // reabrir una archivada: confirm (Enter otra vez) → busy → listo (o error / avisos)
  const [reopen, setReopen] = useState<{ key: string; phase: "confirm" | "busy" | "error" | "warn"; msg?: string } | null>(null);
  useEffect(() => {
    if (!open) return;
    setQ(""); setIndex(0); setReopen(null); setTimeout(() => input.current?.focus(), 0);
    getWs().request("sessions.archived", {}).then((r) => setArchived((r as { sessions: Archived[] }).sessions ?? []))
      .catch(() => setArchived([]));
  }, [open]);

  const all: Item[] = useMemo(() => tree.sessions.map((s) => {
    const k = `s:${s.id}`;
    const tag = s.kind === "main" ? "Manager" : s.kind === "ide" ? "IDE" : s.kind === "recursos" ? "Recursos"
      : s.kind === "review" ? "Revisión" : null;
    const n = tree.devIndex?.[k] ?? (/^\d+$/.test(s.id) ? Number(s.id) : null);
    return { key: k, n, title: tree.devNames?.[k] ?? s.title ?? tag ?? s.id, tag, dot: ACTIVITY[activityOf(s)] };
  }), [tree]);
  const live = useMemo(() => new Set(tree.sessions.map((s) => s.id)), [tree]);
  // las PRs abiertas que conoce el IDE: abren el desarrollo que las tiene (su sesión de ticket o de revisión)
  const { gh } = useGithubReviews();
  const prItems: Item[] = useMemo(() => {
    if (!gh) return [];
    const owners = new Map<string, string>();
    const tickets = tree.sessions.filter((s) => s.kind !== "review");
    for (const d of deriveMine(tickets, gh, tree.devPrs)) if (d.session) for (const p of d.prs) owners.set(p.url, d.session.id);
    for (const s of tree.sessions) if (s.kind === "review") for (const u of s.stackPrs ?? (s.prUrl ? [s.prUrl] : [])) owners.set(u, s.id);
    const ids = new Set(tree.sessions.map((s) => s.id));
    return allPrs(gh).map((p) => {
      const sid = owners.get(p.url) ?? (ids.has(p.sessionId) ? p.sessionId : null);
      const n = sid ? tree.devIndex?.[`s:${sid}`] : undefined;
      return { key: `pr:${p.url}`, n: null, title: p.title, dot: null,
        tag: sid ? `PR · ${n ? `#${n}` : sid}` : "PR sin sesión",
        pr: { label: `${repoShort(p.repo)} #${p.number}`, number: p.number, go: sid ? `s:${sid}` : `p:${p.url}` } };
    });
  }, [gh, tree]);
  const old: Item[] = useMemo(() => archived.filter((a) => !live.has(a.id)).map((a) => ({
    key: `s:${a.id}`, n: a.n, title: a.title ?? a.id, tag: "Archivada", dot: null, archived: true })), [archived, live]);

  const results = useMemo(() => {
    const query = q.trim();
    if (!query) {
      const order = recentKeys();
      const rank = (k: string) => { const i = order.indexOf(k); return i < 0 ? order.length : i; };
      return [...all].sort((a, b) => rank(a.key) - rank(b.key));
    }
    const num = query.replace(/^#/, "");
    // por número: el exacto, después los que empiezan así, después los que lo contienen
    const byNumber = /^\d+$/.test(num) ? all.filter((x) => x.n !== null && String(x.n).includes(num))
      .sort((a, b) => {
        const r = (x: Item) => String(x.n) === num ? 0 : String(x.n).startsWith(num) ? 1 : 2;
        return r(a) - r(b) || a.n! - b.n!;
      }) : [];
    const seen = new Set(byNumber.map((x) => x.key));
    const named = (list: Item[]) => list.filter((x) => !seen.has(x.key))
      .map((x) => ({ x, sc: fuzzy(query, `${x.title} ${x.tag ?? ""} ${x.key.slice(2)}`) }))
      .filter((r) => r.sc !== null).sort((a, b) => b.sc! - a.sc!).map((r) => r.x);
    // las archivadas, después de todas las abiertas (también por número primero)
    const oldByNumber = /^\d+$/.test(num) ? old.filter((x) => x.n !== null && String(x.n).includes(num))
      .sort((a, b) => (String(a.n) === num ? 0 : 1) - (String(b.n) === num ? 0 : 1) || a.n! - b.n!) : [];
    oldByNumber.forEach((x) => seen.add(x.key));
    // PRs: por número (el exacto primero) y por repo + título
    const prByNumber = /^\d+$/.test(num) ? prItems.filter((x) => String(x.pr!.number).includes(num))
      .sort((a, b) => (String(a.pr!.number) === num ? 0 : 1) - (String(b.pr!.number) === num ? 0 : 1) || a.pr!.number - b.pr!.number) : [];
    prByNumber.forEach((x) => seen.add(x.key));
    const prNamed = prItems.filter((x) => !seen.has(x.key))
      .map((x) => ({ x, sc: fuzzy(query, `${x.pr!.label} ${x.title}`) }))
      .filter((r) => r.sc !== null).sort((a, b) => b.sc! - a.sc!).map((r) => r.x);
    return [...byNumber, ...prByNumber, ...named(all), ...prNamed, ...oldByNumber, ...named(old)];
  }, [q, all, old, prItems]);

  useEffect(() => { setIndex(0); setReopen(null); }, [q]);
  useEffect(() => { setReopen((r) => (r?.phase === "confirm" ? null : r)); }, [index]);
  useEffect(() => { sel.current?.scrollIntoView({ block: "nearest" }); }, [index]);
  if (!open) return null;
  const close = () => useSearch.setState({ open: false });
  const pick = (it?: Item) => {
    if (!it) return;
    if (it.pr) { close(); go(it.pr.go); return; }
    if (!it.archived) { close(); go(it.key); return; }
    if (reopen?.key === it.key && reopen.phase === "warn") { close(); go(it.key); return; }
    if (reopen?.key !== it.key || reopen.phase === "error") { setReopen({ key: it.key, phase: "confirm" }); return; }
    if (reopen.phase !== "confirm") return;
    setReopen({ key: it.key, phase: "busy" });
    getWs().request("sessions.unarchive", { id: it.key.slice(2) }).then((r) => {
      const w = (r as { warnings?: string[] }).warnings ?? [];
      if (w.length) setReopen({ key: it.key, phase: "warn", msg: w.join(" · ") });
      else { close(); go(it.key); }
    }).catch((e: unknown) => setReopen({ key: it.key, phase: "error", msg: e instanceof Error ? e.message : String(e) }));
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = results.length; if (!n) return;
      setIndex((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + n) % n);
    } else if (e.key === "Enter") { e.preventDefault(); pick(results[index]); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  };
  return (
    <div className="fixed inset-0 z-[100] flex justify-center bg-black/15 pt-[18vh]" onMouseDown={close}>
      <div onMouseDown={(e) => e.stopPropagation()}
        className="flex h-fit max-h-[60vh] w-[640px] max-w-[92vw] flex-col overflow-hidden rounded-2xl border border-border shadow-[0_24px_80px_rgba(0,0,0,0.45)]"
        style={{ background: "color-mix(in srgb, var(--popover) 96%, transparent)", backdropFilter: "blur(24px) saturate(1.4)" }}>
        <div className="flex items-center gap-3 px-4 py-3">
          <Search size={20} className="shrink-0 text-muted-foreground" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey}
            placeholder="Buscar sesión o PR por número o nombre…" aria-label="Buscar sesión o PR"
            className="min-w-0 flex-1 bg-transparent text-lg text-popover-foreground outline-none placeholder:text-muted-foreground" />
        </div>
        {results.length > 0 ? (
          <div role="listbox" aria-label="Sesiones" className="overflow-y-auto border-t border-border p-1.5">
            {results.map((it, i) => {
              const on = i === index;
              return (
                <button key={it.key} ref={on ? sel : undefined} role="option" aria-selected={on}
                  title={it.pr ? `Abrir ${it.pr.label} (${it.pr.go.startsWith("s:") ? "su desarrollo" : "la card de la PR"})` : it.archived ? `Reabrir ${it.title} (archivada): vuelven su carpeta, worktrees y rama, y se retoma su claude` : `Abrir ${it.title}`}
                  onMouseMove={(e) => { if ((e.movementX || e.movementY) && i !== index) setIndex(i); }}
                  onClick={() => pick(it)}
                  className={cn("flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm",
                    on ? "bg-primary/20 text-foreground" : it.archived ? "text-muted-foreground" : "text-popover-foreground")}
                  style={on ? { background: "color-mix(in srgb, var(--primary) 22%, transparent)" } : undefined}>
                  {it.dot && <span aria-hidden className={cn("w-3 text-xs", it.dot[1])}>{it.dot[0]}</span>}
                  <span className={cn("shrink-0 font-mono font-bold text-primary", it.pr ? "min-w-12 whitespace-nowrap" : "w-12")}>
                    {it.pr ? it.pr.label : it.n ? `#${it.n}` : ""}</span>
                  <span className="min-w-0 flex-1 truncate">{it.title}</span>
                  {reopen?.key === it.key ? (
                    <span className={cn("shrink-0 text-[11px]", reopen.phase === "error" ? "text-destructive" : "text-yellow-300")}>
                      {reopen.phase === "confirm" ? "Enter otra vez para reabrir" : reopen.phase === "busy" ? "Reabriendo…"
                        : reopen.phase === "warn" ? "Reabierta · Enter para ir" : "No se pudo reabrir"}</span>
                  ) : it.tag && <span className="shrink-0 text-[11px] text-muted-foreground">{it.tag}</span>}
                </button>);
            })}
          </div>
        ) : q.trim() ? <div className="border-t border-border px-4 py-3 text-sm text-muted-foreground">Sin resultados</div> : null}
        {reopen?.msg && <div className={cn("border-t border-border px-4 py-2 text-xs", reopen.phase === "error" ? "text-destructive" : "text-yellow-300")}>
          {reopen.msg}</div>}
      </div>
    </div>
  );
}
