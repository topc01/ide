// ui/src/lib/openExternal.ts
/** Abrir algo en una pestaña del navegador. Instalado como app (PWA), `window.open` y los links con
 *  `target="_blank"` abren una ventana de la app: ahí se le pide al server que lo abra en tu navegador
 *  (`POST /api/ui/open`). En una pestaña normal, `window.open` de siempre. */
const standalone = () => {
  try { return matchMedia("(display-mode: standalone)").matches || matchMedia("(display-mode: window-controls-overlay)").matches; }
  catch { return false; }
};

export function openExternal(url: string): void {
  const abs = new URL(url, location.href).href;
  if (!standalone()) { window.open(abs, "_blank", "noopener,noreferrer"); return; }
  fetch("/api/ui/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: abs }) })
    .then((r) => { if (!r.ok) throw new Error(String(r.status)); })
    .catch(() => window.open(abs, "_blank", "noopener,noreferrer"));   // sin server: al menos se abre
}

/** Los `<a target="_blank">` de toda la UI pasan por `openExternal` (en fase de captura: también los que
 *  cortan la propagación del click). Solo en la app instalada. */
export function interceptBlankLinks(): void {
  document.addEventListener("click", (e) => {
    if (!standalone() || e.button !== 0 || e.defaultPrevented) return;
    const a = (e.target as HTMLElement | null)?.closest?.("a[target=_blank]") as HTMLAnchorElement | null;
    if (!a?.href || a.hasAttribute("download") || !/^https?:/i.test(a.href)) return;
    e.preventDefault();
    openExternal(a.href);
  }, true);
}
