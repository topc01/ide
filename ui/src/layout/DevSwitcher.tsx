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
  useEffect(() => { sel.current?.scrollIntoView({ block: "nearest", inline: "center" }); }, [index, open]);
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
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-black/30 backdrop-blur-[2px]">
      <div className="flex max-w-[90vw] gap-2 overflow-x-auto rounded-2xl border border-border/60 bg-popover/85 p-3 shadow-2xl">
        {items.map((k, i) => {
          const d = info(k);
          return (
            <button key={k} ref={i === index ? sel : undefined} title={d.title}
              onMouseEnter={() => useSwitcher.setState({ index: i })}
              onClick={() => { useSwitcher.setState({ index: i }); window.dispatchEvent(new KeyboardEvent("keyup", { key: "Meta" })); }}
              className={cn("flex w-36 shrink-0 flex-col gap-1 rounded-xl border p-2.5 text-left transition-colors",
                i === index ? "border-primary bg-primary/15" : "border-transparent hover:bg-accent/60")}>
              <span className="flex items-center gap-1.5 font-mono text-sm font-bold text-primary">
                {d.dot && <span className={cn("text-[10px]", d.dot[1])}>{d.dot[0]}</span>}
                {d.n ? `#${d.n}` : d.tag ?? ""}
                {d.n && d.tag && <span className="text-[10px] font-normal text-muted-foreground">{d.tag}</span>}
              </span>
              <span className="line-clamp-3 text-xs leading-snug text-foreground">{d.title}</span>
            </button>);
        })}
      </div>
    </div>
  );
}
