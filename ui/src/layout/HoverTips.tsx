// ui/src/layout/HoverTips.tsx
import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** Lo que flota abierto (listas, detalles, menús, diálogos): un tooltip nunca lo tapa. */
const FLOATING = "[data-float],[role=listbox],[role=dialog],[role=menu],[data-radix-popper-content-wrapper]";
const GAP = 6, MARGIN = 8;

type Rect = { left: number; top: number; right: number; bottom: number };
const hits = (a: Rect, b: Rect) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;

/** Tooltips de toda la app: cualquier elemento con `title` muestra su texto en un globo dibujado
 *  en la página (sale en las capturas de pantalla, el nativo del navegador no). Se pasa `title`
 *  a `data-tip` al primer hover para que el navegador no muestre además el suyo. El globo busca un lado
 *  del elemento (abajo, arriba, derecha, izquierda) donde no tape nada de lo que flota abierto; si no hay, no sale. */
export function HoverTips() {
  const [tip, setTip] = useState<{ text: string; anchor: Rect } | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let timer: number | undefined;
    let current: Element | null = null;
    const hide = () => { window.clearTimeout(timer); current = null; setTip(null); setPos(null); };
    const over = (e: MouseEvent) => {
      const el = (e.target as Element | null)?.closest?.("[title],[data-tip]");
      if (el === current) return;
      hide();
      if (!el) return;
      const title = el.getAttribute("title");
      if (title) { el.setAttribute("data-tip", title); el.removeAttribute("title"); }
      const text = el.getAttribute("data-tip");
      if (!text) return;
      current = el;
      timer = window.setTimeout(() => {
        const r = el.getBoundingClientRect();
        setTip({ text, anchor: { left: r.left, top: r.top, right: r.right, bottom: r.bottom } });
      }, 350);
    };
    document.addEventListener("mouseover", over);
    document.addEventListener("mousedown", hide, true);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("blur", hide);
    return () => {
      document.removeEventListener("mouseover", over);
      document.removeEventListener("mousedown", hide, true);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("blur", hide);
    };
  }, []);
  // se mide el globo (invisible) y se elige el primer lado libre
  useLayoutEffect(() => {
    if (!tip || !box.current) return;
    const w = box.current.offsetWidth, h = box.current.offsetHeight;
    const a = tip.anchor, W = window.innerWidth, H = window.innerHeight;
    const clampX = (x: number) => Math.max(MARGIN, Math.min(x, W - w - MARGIN));
    const clampY = (y: number) => Math.max(MARGIN, Math.min(y, H - h - MARGIN));
    const cx = clampX((a.left + a.right) / 2 - w / 2), cy = clampY((a.top + a.bottom) / 2 - h / 2);
    const tries = [
      { left: cx, top: a.bottom + GAP }, { left: cx, top: a.top - GAP - h },
      { left: a.right + GAP, top: cy }, { left: a.left - GAP - w, top: cy },
    ];
    // lo marcado como flotante y todo lo que se abre en un portal (hijos directos de <body> fuera de la app, y sus
    // hijos: los menús de la card, la lista de la barra…), si se ve
    const app = document.getElementById("root");
    const portals = [...document.body.children].filter((n) => n !== app && n !== box.current && n.tagName !== "SCRIPT");
    const nodes = new Set<Element>([...document.querySelectorAll(FLOATING), ...portals,
      ...portals.flatMap((n) => [...n.children])]);
    const obstacles = [...nodes].filter((n) => {
      const cs = getComputedStyle(n);
      return cs.visibility !== "hidden" && cs.display !== "none" && Number(cs.opacity) > 0.05;
    }).map((n) => n.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0);
    const ok = tries.find((t) => {
      const r = { left: t.left, top: t.top, right: t.left + w, bottom: t.top + h };
      return r.left >= MARGIN - 0.5 && r.top >= MARGIN - 0.5 && r.right <= W - MARGIN + 0.5 && r.bottom <= H - MARGIN + 0.5
        && !hits(r, a) && !obstacles.some((o) => hits(r, o));
    });
    setPos(ok ?? null);
  }, [tip]);
  if (!tip) return null;
  return (
    <div ref={box} role="tooltip" style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: "hidden" }}
      className="pointer-events-none fixed z-[100] max-w-xs whitespace-pre-wrap break-words rounded-md border border-border bg-popover px-2 py-1 text-[11px] text-popover-foreground shadow-md">
      {tip.text}
    </div>
  );
}
