import { create } from "zustand";

/** Tema de la UI: oscuro (el de siempre), claro, o el del sistema (sigue al modo del computador, también
 *  cuando cambia con el IDE abierto). Se guarda en este navegador; `index.html` lo aplica antes de pintar
 *  para que no parpadee. `theme` es el que se ve; `pref`, lo elegido. */
export type Theme = "dark" | "light";
export type ThemePref = Theme | "system";
const KEY = "ide.theme";
const NEXT: Record<ThemePref, ThemePref> = { dark: "light", light: "system", system: "dark" };

const media = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

function saved(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "system" ? v : "dark";
  } catch { return "dark"; }
}

const resolve = (p: ThemePref): Theme => (p === "system" ? (media?.matches ? "light" : "dark") : p);

function apply(t: Theme) {
  document.documentElement.classList.toggle("light", t === "light");
}

export const useTheme = create<{ pref: ThemePref; theme: Theme; toggle: () => void }>((set, get) => ({
  pref: saved(),
  theme: resolve(saved()),
  toggle: () => {
    const pref = NEXT[get().pref];
    try { localStorage.setItem(KEY, pref); } catch { /* sin storage: solo esta vez */ }
    const theme = resolve(pref);
    apply(theme);
    set({ pref, theme });
  },
}));

// en "sistema", cambiar el modo del computador cambia el IDE al tiro
media?.addEventListener("change", () => {
  const { pref } = useTheme.getState();
  if (pref !== "system") return;
  const theme = resolve(pref);
  apply(theme);
  useTheme.setState({ theme });
});
