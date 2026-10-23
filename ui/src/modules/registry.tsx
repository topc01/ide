import type { LucideIcon } from "lucide-react";
import type { PanelId } from "../state/store";

/** `useBadge`: hook opcional con un conteo para el ícono del menú de acciones (null/0 = sin marca). */
export interface ActivityModule { id: PanelId; title: string; icon: LucideIcon; Panel: React.FC; useBadge?: () => number | null; }
const modules: ActivityModule[] = [];
export function registerModule(m: ActivityModule) {
  if (!modules.some((x) => x.id === m.id)) modules.push(m);
}
export function getModules(): ActivityModule[] { return modules; }
