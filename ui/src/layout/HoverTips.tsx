// ui/src/layout/HoverTips.tsx
import { useEffect, useState } from "react";

/** Tooltips de toda la app: cualquier elemento con `title` muestra su texto en un globo dibujado
 *  en la página (sale en las capturas de pantalla, el nativo del navegador no). Se pasa `title`
 *  a `data-tip` al primer hover para que el navegador no muestre además el suyo. */
export function HoverTips() {
  const [tip, setTip] = useState<{ text: string; x: number; y: number; below: boolean;
                                    align: "left" | "center" | "right" } | null>(null);
  useEffect(() => {
    let timer: number | undefined;
    let current: Element | null = null;
    const hide = () => { window.clearTimeout(timer); current = null; setTip(null); };
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
        const below = r.bottom + 40 < window.innerHeight;
        // cerca de un borde el globo se alinea a ese borde (centrado se cortaría): ~ancho máx 320px
        const cx = r.left + r.width / 2;
        const align = cx < 170 ? "left" : cx > window.innerWidth - 170 ? "right" : "center";
        const x = align === "left" ? Math.max(r.left, 8) : align === "right" ? Math.min(r.right, window.innerWidth - 8) : cx;
        setTip({ text, x, y: below ? r.bottom + 6 : r.top - 6, below, align });
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
  if (!tip) return null;
  return (
    <div role="tooltip" style={{ left: tip.x, top: tip.y,
      transform: `translate(${tip.align === "left" ? "0" : tip.align === "right" ? "-100%" : "-50%"}, ${tip.below ? "0" : "-100%"})` }}
      className="pointer-events-none fixed z-[100] max-w-xs whitespace-pre-wrap break-words rounded-md border border-border bg-popover px-2 py-1 text-[11px] text-popover-foreground shadow-md">
      {tip.text}
    </div>
  );
}
