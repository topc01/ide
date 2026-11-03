// ui/src/layout/devShortcuts.ts
/** Atajos para cambiar de desarrollo:
 *  - ⌘↑ / ⌘↓: el anterior / el siguiente en el orden de la sidebar (las cards visibles).
 *  - ⌘→: abre el selector (como ⌘Tab de macOS): los desarrollos por último acceso, con el anterior marcado;
 *    con ⌘ apretado, → y ← mueven la selección; al soltar ⌘ se abre el marcado; Esc lo cierra sin cambiar.
 *  - ⌘K: abre / cierra el buscador de sesiones (DevSearch), también escribiendo en un campo.
 *  No se activan escribiendo en un campo de texto (ahí ⌘←/⌘→ mueven el cursor); en la terminal sí. */
import { useEffect } from "react";
import { create } from "zustand";
import { useFolders } from "../state/folders";

type Key = string;                       // "s:<id>" (sesión) | "p:<url>" (PR sin sesión)
const keyOf = (s: { activeId: string | null; activePrUrl: string | null }): Key | null =>
  s.activePrUrl ? `p:${s.activePrUrl}` : s.activeId ? `s:${s.activeId}` : null;

const recent: Key[] = [];                 // orden de acceso: el más reciente primero
let walking = false;

/** El buscador de ⌘K. */
export const useSearch = create<{ open: boolean }>(() => ({ open: false }));

/** Los desarrollos por último acceso (el más reciente primero). */
export const recentKeys = (): Key[] => recent.filter((k) => valid(k));

/** El selector abierto: la lista (foto del orden de acceso al abrirlo) y el marcado. */
export const useSwitcher = create<{ open: boolean; items: Key[]; index: number }>(() => ({ open: false, items: [], index: 0 }));

useFolders.subscribe((s, prev) => {
  const k = keyOf(s);
  if (!k || k === keyOf(prev)) return;
  if (walking) walking = false;
  const i = recent.indexOf(k);
  if (i >= 0) recent.splice(i, 1);
  recent.unshift(k);
  if (recent.length > 50) recent.pop();
});
{ const k = keyOf(useFolders.getState()); if (k) recent.push(k); }

export function go(k: Key) {
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
  const sw = useSwitcher.getState();
  if (!sw.open) {
    if (step < 0) return;                         // se abre con ⌘→
    const items = recent.filter((k) => valid(k));
    if (items.length < 2) return;
    useSwitcher.setState({ open: true, items, index: 1 });
    return;
  }
  const n = sw.items.length;
  useSwitcher.setState({ index: (sw.index + step + n) % n });
}

/** Que el desarrollo siga existiendo (una sesión archivada sale de la lista). */
function valid(k: Key): boolean {
  if (k.startsWith("p:")) return true;
  return useFolders.getState().tree.sessions.some((s) => s.id === k.slice(2));
}

function closeSwitcher(pick: boolean) {
  const sw = useSwitcher.getState();
  if (!sw.open) return;
  useSwitcher.setState({ open: false });
  const k = sw.items[sw.index];
  if (pick && k && k !== keyOf(useFolders.getState())) go(k);
}

export function useDevShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey && !e.altKey && !e.ctrlKey && !e.shiftKey && (e.code === "KeyK" || e.key.toLowerCase() === "k")) {
        e.preventDefault(); e.stopPropagation();
        closeSwitcher(false);
        useSearch.setState({ open: !useSearch.getState().open });
        return;
      }
      if (useSwitcher.getState().open && e.key === "Escape") { e.preventDefault(); closeSwitcher(false); return; }
      if (!e.metaKey || e.altKey || e.ctrlKey || e.shiftKey || typing(e.target)) return;
      const sw = useSwitcher.getState().open;     // con el selector abierto, solo ← y →
      const act = { ArrowUp: () => !sw && bySidebar(-1), ArrowDown: () => !sw && bySidebar(1),
        ArrowRight: () => byAccess(1), ArrowLeft: () => byAccess(-1) }[e.key];
      if (!act) return;
      e.preventDefault(); e.stopPropagation();         // ⌘←/⌘→ del navegador = atrás/adelante: no
      act();
    };
    // al soltar ⌘ se abre el marcado; si la ventana pierde el foco (⌘Tab de verdad), se cierra sin cambiar
    const onUp = (e: KeyboardEvent) => { if (e.key === "Meta") closeSwitcher(true); };
    const onBlur = () => closeSwitcher(false);
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("keyup", onUp, true);
    window.addEventListener("blur", onBlur);
    return () => { window.removeEventListener("keydown", onKey, true); window.removeEventListener("keyup", onUp, true);
      window.removeEventListener("blur", onBlur); };
  }, []);
}
