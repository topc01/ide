// ui/src/main/pathLinks.ts
import type { FolderSession } from "../transport/folderSessions";

/** A dónde lleva una ruta que claude mencionó en su terminal: un adjunto de la sesión o un archivo de
 *  uno de sus worktrees. */
export type PathTarget = { kind: "attachment"; name: string } | { kind: "file"; repo: string; path: string };

/** Lo que parece una ruta en una línea de la terminal: con al menos una `/` (absoluta, `./…` o relativa),
 *  y quizás `:línea[:columna]` al final. */
export const PATH_RE = /(?:~|\.)?\/?[\w.@+-]+(?:\/[\w.@+-]+)+(?::\d+(?::\d+)?)?/g;

/** `raw` (como salió en la terminal) → su destino en la sesión, o null si no es de ella. Acepta la ruta
 *  absoluta de la carpeta de la sesión o de sus worktrees, o relativa a la carpeta (`attachments/…`,
 *  `finnecto-api/…`, que son los worktrees). */
export function resolvePath(raw: string, session: FolderSession): PathTarget | null {
  let p = raw.replace(/:\d+(?::\d+)?$/, "").replace(/[.,;)]+$/, "");
  const wts = session.path.replace(/\/sessions\/([^/]+)$/, "/worktrees/$1");
  if (p.startsWith(`${session.path}/`)) p = p.slice(session.path.length + 1);
  else if (p.startsWith(`${wts}/`)) p = p.slice(wts.length + 1);
  else if (p.startsWith("/") || p.startsWith("~")) return null;
  p = p.replace(/^\.\//, "");
  if (p.startsWith("attachments/") && p.length > "attachments/".length) return { kind: "attachment", name: p.slice("attachments/".length) };
  const [first, ...rest] = p.split("/");
  if (rest.length && session.repos.some((r) => r.name === first)) return { kind: "file", repo: first, path: rest.join("/") };
  return null;
}
