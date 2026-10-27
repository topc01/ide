import { create } from "zustand";

/** Tema de la UI: oscuro (el de siempre) o claro. Se guarda en este navegador; `index.html` lo aplica
 *  antes de pintar para que no parpadee. Las terminales siguen oscuras en los dos. */
export type Theme = "dark" | "light";
const KEY = "ide.theme";

function saved(): Theme {
  try { return localStorage.getItem(KEY) === "light" ? "light" : "dark"; } catch { return "dark"; }
}

function apply(t: Theme) {
  document.documentElement.classList.toggle("light", t === "light");
}

export const useTheme = create<{ theme: Theme; toggle: () => void }>((set, get) => ({
  theme: saved(),
  toggle: () => {
    const t: Theme = get().theme === "light" ? "dark" : "light";
    try { localStorage.setItem(KEY, t); } catch { /* sin storage: solo esta vez */ }
    apply(t);
    set({ theme: t });
  },
}));
