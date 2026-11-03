// ui/src/layout/DevSearch.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { go, recentKeys, useSearch } from "./devShortcuts";
import { useFolders } from "../state/folders";
import { ACTIVITY, activityOf } from "../modules/sessions/activity";
import { cn } from "../lib/utils";

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

type Item = { key: string; n: number | null; title: string; tag: string | null; dot: [string, string, string] | null };

/** ⌘K (como Spotlight): un input y abajo las sesiones que calzan, por número primero (`12`, `#12`) y
 *  después por nombre (fuzzy). ↑/↓ mueven, Enter abre, Esc o ⌘K otra vez cierran. Vacío: por último
 *  acceso. */
export function DevSearch() {
  const open = useSearch((s) => s.open);
  const tree = useFolders((s) => s.tree);
  const [q, setQ] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const sel = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (open) { setQ(""); setIndex(0); setTimeout(() => input.current?.focus(), 0); } }, [open]);

  const all: Item[] = useMemo(() => tree.sessions.map((s) => {
    const k = `s:${s.id}`;
    const tag = s.kind === "main" ? "Manager" : s.kind === "ide" ? "IDE" : s.kind === "recursos" ? "Recursos"
      : s.kind === "review" ? "Revisión" : null;
    const n = tree.devIndex?.[k] ?? (/^\d+$/.test(s.id) ? Number(s.id) : null);
    return { key: k, n, title: tree.devNames?.[k] ?? s.title ?? tag ?? s.id, tag, dot: ACTIVITY[activityOf(s)] };
  }), [tree]);

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
    const byName = all.filter((x) => !seen.has(x.key))
      .map((x) => ({ x, sc: fuzzy(query, `${x.title} ${x.tag ?? ""} ${x.key.slice(2)}`) }))
      .filter((r) => r.sc !== null).sort((a, b) => b.sc! - a.sc!).map((r) => r.x);
    return [...byNumber, ...byName];
  }, [q, all]);

  useEffect(() => { setIndex(0); }, [q]);
  useEffect(() => { sel.current?.scrollIntoView({ block: "nearest" }); }, [index]);
  if (!open) return null;
  const close = () => useSearch.setState({ open: false });
  const pick = (it?: Item) => { if (!it) return; close(); go(it.key); };
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
            placeholder="Buscar sesión por número o nombre…" aria-label="Buscar sesión"
            className="min-w-0 flex-1 bg-transparent text-lg text-popover-foreground outline-none placeholder:text-muted-foreground" />
        </div>
        {results.length > 0 ? (
          <div role="listbox" aria-label="Sesiones" className="overflow-y-auto border-t border-border p-1.5">
            {results.map((it, i) => {
              const on = i === index;
              return (
                <button key={it.key} ref={on ? sel : undefined} role="option" aria-selected={on} title={`Abrir ${it.title}`}
                  onMouseMove={(e) => { if ((e.movementX || e.movementY) && i !== index) setIndex(i); }}
                  onClick={() => pick(it)}
                  className={cn("flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm",
                    on ? "bg-primary/20 text-foreground" : "text-popover-foreground")}
                  style={on ? { background: "color-mix(in srgb, var(--primary) 22%, transparent)" } : undefined}>
                  {it.dot && <span aria-hidden className={cn("w-3 text-xs", it.dot[1])}>{it.dot[0]}</span>}
                  <span className="w-12 shrink-0 font-mono font-bold text-primary">{it.n ? `#${it.n}` : ""}</span>
                  <span className="min-w-0 flex-1 truncate">{it.title}</span>
                  {it.tag && <span className="shrink-0 text-[11px] text-muted-foreground">{it.tag}</span>}
                </button>);
            })}
          </div>
        ) : q.trim() ? <div className="border-t border-border px-4 py-3 text-sm text-muted-foreground">Sin resultados</div> : null}
      </div>
    </div>
  );
}
