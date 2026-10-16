// ui/src/modules/sessions/OffscreenMarker.tsx
import { useEffect, useState, type RefObject } from "react";

/** Dónde quedó la card seleccionada (`[aria-current]`) respecto de la zona visible del scroll. */
export function useOffscreenSelected(container: RefObject<HTMLElement | null>, key: unknown) {
  const [where, setWhere] = useState<"above" | "below" | null>(null);
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    let frame = 0;
    const check = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sel = el.querySelector<HTMLElement>('[aria-current="true"]');
        if (!sel) { setWhere(null); return; }
        const box = el.getBoundingClientRect(), r = sel.getBoundingClientRect();
        setWhere(r.bottom < box.top + 8 ? "above" : r.top > box.bottom - 8 ? "below" : null);
      });
    };
    check();
    el.addEventListener("scroll", check, { passive: true });
    const ro = new ResizeObserver(check);
    ro.observe(el);
    const mo = new MutationObserver(check);      // las cards cambian (poll, grupos que se abren)
    mo.observe(el, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-current", "data-state"] });
    return () => { el.removeEventListener("scroll", check); ro.disconnect(); mo.disconnect(); cancelAnimationFrame(frame); };
  }, [container, key]);
  return where;
}

/** Raya amarilla fija arriba/abajo cuando el desarrollo seleccionado quedó fuera de la vista. */
export function OffscreenMarker({ where, side, container }:
  { where: "above" | "below" | null; side: "above" | "below"; container: RefObject<HTMLElement | null> }) {
  if (where !== side) return null;
  return (
    <button aria-label="Ir al desarrollo seleccionado"
      title={`El desarrollo seleccionado está más ${side === "above" ? "arriba" : "abajo"}: click para ir`}
      onClick={() => container.current?.querySelector<HTMLElement>('[aria-current="true"]')
        ?.scrollIntoView({ block: "center", behavior: "smooth" })}
      className={`sticky z-20 block h-1.5 w-full shrink-0 bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,.6)] transition-[height] hover:h-2.5 ${side === "above" ? "top-0" : "bottom-0"}`} />
  );
}
