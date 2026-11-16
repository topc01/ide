// ui/src/modules/later/ask.ts
/** Abrir la sesión de un bloqueante con «Sobre la decisión D3 («…»): » escrito en su claude (sin mandar), para
 *  preguntarle o comentarle algo sobre ese bloqueante. */
import { useFolders } from "../../state/folders";
import { typeIntoClaude } from "../../transport/terminalChannel";
import { getWs } from "../../transport/wsClient";
import type { LaterItem } from "../../transport/folderSessions";

export const laterCode = (it: Pick<LaterItem, "kind" | "num">) => `${it.kind === "pending" ? "P" : "D"}${it.num ?? "?"}`;

export function openSessionOf(it: LaterItem) {
  if (it.key.startsWith("s:") && !it.archived) useFolders.getState().setActive(it.key.slice(2));
}

export function askAbout(it: LaterItem) {
  if (!it.key.startsWith("s:") || it.archived) return;
  const sid = it.key.slice(2);
  const st = useFolders.getState();
  const had = st.tree.sessions.find((x) => x.id === sid)?.terminalId;
  st.setActive(sid);
  const text = `Sobre ${it.kind === "pending" ? "el pendiente" : "la decisión"} ${laterCode(it)} («${it.text.slice(0, 120)}${it.text.length > 120 ? "…" : ""}»): `;
  const t0 = Date.now();
  const tick = () => {
    const tid = useFolders.getState().tree.sessions.find((x) => x.id === sid)?.terminalId;
    if (!tid) { if (Date.now() - t0 < 30000) window.setTimeout(tick, 300); return; }
    // si su claude recién arrancó, se espera a que esté listo para escribir (si no, se pierde lo tecleado)
    window.setTimeout(() => {
      typeIntoClaude(getWs(), tid, text).then(() => {
        (document.querySelector(".xterm-helper-textarea") as HTMLTextAreaElement | null)?.focus();
      }).catch(() => undefined);
    }, had ? 300 : 6000);
  };
  tick();
}
