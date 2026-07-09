import type { LucideIcon } from "lucide-react";
import type { PanelId } from "../state/store";

export interface ActivityModule { id: PanelId; title: string; icon: LucideIcon; Panel: React.FC; }
const modules: ActivityModule[] = [];
export function registerModule(m: ActivityModule) {
  if (!modules.some((x) => x.id === m.id)) modules.push(m);
}
export function getModules(): ActivityModule[] { return modules; }
