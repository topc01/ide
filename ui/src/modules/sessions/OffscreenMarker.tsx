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

/** Cerca del puntero (estilo dock): a la misma altura crece; más cerca del borde, más; muy cerca
 *  se despliega mostrando la card del desarrollo seleccionado. */
function useProximity(container: RefObject<HTMLElement | null>, side: "above" | "below", active: boolean) {
  const [level, setLevel] = useState(0);              // 0 nada · 1 misma altura · 2 cerca · 3 desplegada
  useEffect(() => {
    const el = container.current;
    if (!el || !active) { setLevel(0); return; }
    const move = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      const cy = side === "above" ? r.top + 18 : r.bottom - 18;
      const dy = Math.abs(e.clientY - cy), dx = e.clientX - r.left;
      setLevel(dy > 26 ? 0 : dx <= 60 ? 3 : dx <= 150 ? 2 : 1);
    };
    const leave = () => setLevel(0);
    el.addEventListener("mousemove", move);
    el.addEventListener("mouseleave", leave);
    return () => { el.removeEventListener("mousemove", move); el.removeEventListener("mouseleave", leave); };
  }, [container, side, active]);
  return level;
}

/** Barrita de acento (la misma de la card activa) fija arriba o abajo a la izquierda cuando el
 *  desarrollo seleccionado quedó fuera de la vista; click = scroll hasta él. */
export function OffscreenMarker({ where, side, container }:
  { where: "above" | "below" | null; side: "above" | "below"; container: RefObject<HTMLElement | null> }) {
  const shown = where === side;
  const level = useProximity(container, side, shown);
  if (!shown) return null;
  const selected = container.current?.querySelector<HTMLElement>('[aria-current="true"]');
  // cabecera (repo #n) y título de la card real (mismas clases en cards de PR y de sesión)
  const head = selected?.querySelector(".font-bold")?.textContent?.trim();
  const title = selected?.querySelector(".line-clamp-2")?.textContent?.trim();
  const go = () => selected?.scrollIntoView({ block: "center", behavior: "smooth" });
  const size = ["h-7 w-1", "h-9 w-1.5", "h-11 w-2"][Math.min(level, 2)];
  return (
    <div className={`sticky z-20 h-0 ${side === "above" ? "top-0" : "bottom-0"}`}>
      {level < 3 ? (
        <button aria-label="Ir al desarrollo seleccionado"
          title={`El desarrollo seleccionado está más ${side === "above" ? "arriba" : "abajo"}: click para ir`}
          onClick={go}
          className={`absolute left-0.5 rounded-full bg-primary transition-all duration-150 ${size} ${side === "above" ? "top-1" : "bottom-1"}`} />
      ) : (
        <button aria-label="Ir al desarrollo seleccionado" title="Click para ir al desarrollo seleccionado" onClick={go}
          className={`absolute left-0.5 w-60 animate-in fade-in zoom-in-95 rounded-md border-2 border-primary bg-card px-2 py-1.5 text-left text-xs shadow-lg shadow-black/40 ${side === "above" ? "top-1" : "bottom-1"}`}>
          <span className="absolute -left-0.5 top-1/2 h-7 w-1 -translate-y-1/2 rounded-full bg-primary" />
          <div className="font-mono text-[11px] font-bold">{head}</div>
          {title && <div className="line-clamp-2 leading-snug">{title}</div>}
          <div className="mt-0.5 text-[10px] text-muted-foreground">{side === "above" ? "↑ más arriba" : "↓ más abajo"} · click para ir</div>
        </button>
      )}
    </div>
  );
}
