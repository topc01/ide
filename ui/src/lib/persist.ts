// ui/src/lib/persist.ts
import { useCallback, useState } from "react";

const PREFIX = "ide.open.";

function read(key: string, initial: boolean): boolean {
  try {
    const v = localStorage.getItem(PREFIX + key);
    return v === null ? initial : v === "1";
  } catch { return initial; }          // storage bloqueado: solo memoria
}

/** Abierto/cerrado de una sección, recordado entre recargas (por navegador). */
export function usePersistentOpen(key: string, initial = true): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(() => read(key, initial));
  const set = useCallback((o: boolean) => {
    setOpen(o);
    try { localStorage.setItem(PREFIX + key, o ? "1" : "0"); } catch { /* solo memoria */ }
  }, [key]);
  return [open, set];
}
