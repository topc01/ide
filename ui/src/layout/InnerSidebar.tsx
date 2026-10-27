import { useEffect, useRef, useState } from "react";
import { useStore } from "../state/store";
import { getModules } from "../modules/registry";
import { useFolders } from "../state/folders";
import { ScrollArea } from "../components/ui/scroll-area";

const WIDTH_KEY = "ide.innerSidebarWidth";
const MIN = 200, MAX = 720, DEFAULT = 256;
const clamp = (w: number) => Math.min(MAX, Math.max(MIN, Math.round(w)));

function savedWidth(): number {
  try {
    const w = Number(localStorage.getItem(WIDTH_KEY));
    return w ? clamp(w) : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

export function InnerSidebar() {
  const { activePanel, innerSidebarOpen } = useStore();
  const uiModules = useFolders((s) => s.uiModules);
  const [width, setWidth] = useState(savedWidth);
  const drag = useRef<{ x: number; w: number } | null>(null);
  // arrastrar el borde derecho cambia el ancho; queda guardado en este navegador (doble click = el de siempre)
  useEffect(() => {
    const move = (e: PointerEvent) => { if (drag.current) setWidth(clamp(drag.current.w + e.clientX - drag.current.x)); };
    const up = () => {
      if (!drag.current) return;
      drag.current = null;
      document.body.style.cursor = document.body.style.userSelect = "";
      setWidth((w) => { try { localStorage.setItem(WIDTH_KEY, String(w)); } catch { /* sin storage: solo esta vez */ } return w; });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
  }, []);
  const visible = getModules().filter((m) => !uiModules || uiModules.includes(m.id));
  if (!innerSidebarOpen || visible.length === 0) return null;
  const mod = visible.find((m) => m.id === activePanel) ?? visible[0];
  const Panel = mod?.Panel;
  return (
    <aside className="relative shrink-0 border-r border-border bg-card" style={{ width }}>
      {/* el viewport de Radix envuelve en `display: table` (crece sin límite): bloque, para que trunquen */}
      <ScrollArea className="h-full [&_[data-radix-scroll-area-viewport]>div]:!block">{Panel ? <Panel /> : null}</ScrollArea>
      <div role="separator" aria-orientation="vertical" aria-label="Ancho de la sidebar interna"
        title="Arrastra para cambiar el ancho (se guarda) · doble click: volver al ancho de siempre"
        onPointerDown={(e) => {
          e.preventDefault();
          drag.current = { x: e.clientX, w: width };
          document.body.style.cursor = "col-resize";
          document.body.style.userSelect = "none";
        }}
        onDoubleClick={() => { setWidth(DEFAULT); try { localStorage.removeItem(WIDTH_KEY); } catch { /* nada */ } }}
        className="absolute -right-1 top-0 z-10 h-full w-2 cursor-col-resize hover:bg-primary/30 active:bg-primary/40" />
    </aside>
  );
}
