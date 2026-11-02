// ui/src/layout/DevSwitcher.tsx
import { useEffect, useRef } from "react";
import { useSwitcher } from "./devShortcuts";
import { useFolders } from "../state/folders";
import { ACTIVITY, activityOf } from "../modules/sessions/activity";
import { cn } from "../lib/utils";

/** El selector de ⌘→ (como ⌘Tab): los desarrollos por último acceso, el marcado resaltado. Al soltar ⌘ se
 *  abre (lo maneja devShortcuts); un click también. */
export function DevSwitcher() {
  const { open, items, index } = useSwitcher();
  const tree = useFolders((s) => s.tree);
  const sel = useRef<HTMLButtonElement>(null);
  useEffect(() => { sel.current?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [index, open]);
  if (!open) return null;
  const info = (k: string) => {
    if (k.startsWith("p:")) {
      const m = k.match(/github\.com\/[^/]+\/([^/]+)\/pull\/(\d+)/);
      return { n: null, title: m ? `${m[1].replace(/^finnecto-/, "")}#${m[2]}` : k.slice(2), tag: "PR", dot: null };
    }
    const s = tree.sessions.find((x) => x.id === k.slice(2));
    const tag = s?.kind === "main" ? "Manager" : s?.kind === "ide" ? "IDE" : s?.kind === "recursos" ? "Recursos"
      : s?.kind === "review" ? "Revisión" : null;
    const n = tree.devIndex?.[k] ?? (s && /^\d+$/.test(s.id) ? Number(s.id) : null);
    return { n, title: tree.devNames?.[k] ?? s?.title ?? tag ?? k.slice(2), tag, dot: s ? ACTIVITY[activityOf(s)] : null };
  };
  const cur = info(items[index]);
  // los colores son variables hex (`var(--popover)`): la opacidad de tailwind (`bg-popover/85`) no aplica sobre
  // ellas, así que el fondo se mezcla con color-mix
  const glass = { background: "color-mix(in srgb, var(--popover) 94%, transparent)", backdropFilter: "blur(24px) saturate(1.4)" };
  return (
    <div className="pointer-events-auto fixed inset-0 z-[100] grid place-items-center bg-black/15">
      <div className="flex max-w-[92vw] flex-col items-center gap-3 rounded-3xl border border-border p-5 shadow-[0_24px_80px_rgba(0,0,0,0.45)]"
        style={glass}>
        <div className="flex max-w-full gap-3 overflow-x-auto pb-1">
          {items.map((k, i) => {
            const d = info(k);
            const on = i === index;
            return (
              <button key={k} ref={on ? sel : undefined} title={d.title}
                // solo si el mouse se mueve de verdad: con mouseenter, el scroll de las flechas pasaba
                // tarjetas bajo el puntero quieto y la selección saltaba varias de una vez
                onMouseMove={(e) => { if ((e.movementX || e.movementY) && useSwitcher.getState().index !== i) useSwitcher.setState({ index: i }); }}
                onClick={() => { useSwitcher.setState({ index: i }); window.dispatchEvent(new KeyboardEvent("keyup", { key: "Meta" })); }}
                // las tarjetas, sólidas (el panel es el que deja ver algo de atrás); la marcada, teñida de ámbar
                style={{ background: on ? "color-mix(in srgb, var(--primary) 22%, var(--card))" : "var(--card)" }}
                className={cn("flex h-32 w-44 shrink-0 flex-col justify-between rounded-2xl border p-3 text-left shadow-sm transition-colors",
                  on ? "border-primary ring-2 ring-primary" : "border-border hover:border-primary/50")}>
                <span className="flex items-center gap-2">
                  {d.dot && <span className={cn("text-xs", d.dot[1])}>{d.dot[0]}</span>}
                  <span className="font-mono text-2xl font-bold leading-none text-primary">{d.n ? `#${d.n}` : d.tag ?? "·"}</span>
                  {d.n && d.tag && <span className="text-[11px] text-muted-foreground">{d.tag}</span>}
                </span>
                <span className="line-clamp-3 text-[13px] leading-snug text-popover-foreground">{d.title}</span>
              </button>);
          })}
        </div>
        <div className="max-w-[80vw] truncate text-sm font-medium text-popover-foreground">
          {cur ? `${cur.n ? `#${cur.n} · ` : ""}${cur.title}` : ""}</div>
      </div>
    </div>
  );
}
