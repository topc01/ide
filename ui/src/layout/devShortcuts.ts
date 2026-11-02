// ui/src/layout/devShortcuts.ts
/** Atajos para cambiar de desarrollo:
 *  - ⌘↑ / ⌘↓: el anterior / el siguiente en el orden de la sidebar (las cards visibles).
 *  - ⌘→: el último que tuviste abierto; seguir con ⌘→ va a los anteriores (orden de acceso) y ⌘← vuelve
 *    hacia los más recientes. Elegir uno de otra forma (click, notificación) reinicia el recorrido.
 *  No se activan escribiendo en un campo de texto (ahí ⌘←/⌘→ mueven el cursor); en la terminal sí. */
import { useEffect } from "react";
import { useFolders } from "../state/folders";

type Key = string;                       // "s:<id>" (sesión) | "p:<url>" (PR sin sesión)
const keyOf = (s: { activeId: string | null; activePrUrl: string | null }): Key | null =>
  s.activePrUrl ? `p:${s.activePrUrl}` : s.activeId ? `s:${s.activeId}` : null;

const recent: Key[] = [];                 // orden de acceso: el más reciente primero
let cursor = 0;                           // dónde va el recorrido con ⌘←/⌘→
let walking = false;                      // el cambio lo hizo el recorrido: no reordena

useFolders.subscribe((s, prev) => {
  const k = keyOf(s);
  if (!k || k === keyOf(prev)) return;
  if (walking) { walking = false; return; }
  const i = recent.indexOf(k);
  if (i >= 0) recent.splice(i, 1);
  recent.unshift(k);
  if (recent.length > 50) recent.pop();
  cursor = 0;
});
{ const k = keyOf(useFolders.getState()); if (k) recent.push(k); }

function go(k: Key) {
  const s = useFolders.getState();
  walking = true;
  if (k.startsWith("p:")) s.setActivePr(k.slice(2));
  else s.setActive(k.slice(2));
}

function typing(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  if (el.classList?.contains("xterm-helper-textarea")) return false;   // la terminal: los atajos valen
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || !!el.isContentEditable;
}

function bySidebar(step: 1 | -1) {
  const cards = Array.from(document.querySelectorAll<HTMLElement>("aside [data-card]"));
  if (!cards.length) return;
  const cur = cards.findIndex((c) => c.getAttribute("aria-current") === "true");
  const next = cards[cur < 0 ? (step > 0 ? 0 : cards.length - 1) : Math.min(cards.length - 1, Math.max(0, cur + step))];
  if (next && next !== cards[cur]) { next.click(); next.scrollIntoView({ block: "nearest" }); }
}

function byAccess(step: 1 | -1) {
  // ⌘→ (step 1) hacia atrás en el acceso; ⌘← (step -1) hacia lo más reciente
  const i = Math.min(recent.length - 1, Math.max(0, cursor + step));
  if (i === cursor || !recent[i]) return;
  cursor = i;
  go(recent[i]);
}

export function useDevShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.metaKey || e.altKey || e.ctrlKey || e.shiftKey || typing(e.target)) return;
      const act = { ArrowUp: () => bySidebar(-1), ArrowDown: () => bySidebar(1),
        ArrowRight: () => byAccess(1), ArrowLeft: () => byAccess(-1) }[e.key];
      if (!act) return;
      e.preventDefault(); e.stopPropagation();         // ⌘←/⌘→ del navegador = atrás/adelante: no
      act();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
}
