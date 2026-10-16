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

/** Barrita de acento (la misma de la card activa) fija arriba o abajo a la izquierda cuando el
 *  desarrollo seleccionado quedó fuera de la vista; click = scroll hasta él. */
export function OffscreenMarker({ where, side, container }:
  { where: "above" | "below" | null; side: "above" | "below"; container: RefObject<HTMLElement | null> }) {
  if (where !== side) return null;
  return (
    <div className={`sticky z-20 h-0 ${side === "above" ? "top-0" : "bottom-0"}`}>
      <button aria-label="Ir al desarrollo seleccionado"
        title={`El desarrollo seleccionado está más ${side === "above" ? "arriba" : "abajo"}: click para ir`}
        onClick={() => container.current?.querySelector<HTMLElement>('[aria-current="true"]')
          ?.scrollIntoView({ block: "center", behavior: "smooth" })}
        className={`absolute left-0.5 h-7 w-1 rounded-full bg-primary transition-all hover:h-9 hover:w-1.5 ${side === "above" ? "top-1" : "bottom-1"}`} />
    </div>
  );
}
