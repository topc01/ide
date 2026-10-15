import type { WsClient } from "./ws";

export interface TerminalInfo { id: string; cmd: string[]; alive: boolean; }

export function openTerminal(ws: WsClient,
  opts: { sessionId?: string; repoId?: string; cmd?: string[] }): Promise<{ id: string; cwd: string }> {
  return ws.request("terminal.open", opts);
}
// btoa solo acepta Latin-1: se codifica a UTF-8 antes (acentos, emojis).
const toBase64 = (s: string) =>
  btoa(Array.from(new TextEncoder().encode(s), (b) => String.fromCharCode(b)).join(""));

export function writeTerminal(ws: WsClient, id: string, data: string): Promise<any> {
  return ws.request("terminal.write", { id, data: toBase64(data) });
}

// Pega texto en el input de `claude` sin enviarlo: cada salto de línea va como Option+Enter
// (ESC+CR = nueva línea en el input). Un paste normal se colapsa en "[Pasted text #1]".
export function typeIntoClaude(ws: WsClient, id: string, text: string): Promise<any> {
  return writeTerminal(ws, id, text.replace(/\r\n/g, "\n").replace(/\s+$/, "").split("\n").join("\x1b\r"));
}
export function resizeTerminal(ws: WsClient, id: string, cols: number, rows: number): Promise<any> {
  return ws.request("terminal.resize", { id, cols, rows });
}
export function closeTerminal(ws: WsClient, id: string): Promise<any> {
  return ws.request("terminal.close", { id });
}
export async function listTerminals(ws: WsClient, sessionId: string): Promise<TerminalInfo[]> {
  return (await ws.request("terminal.list", { sessionId })).terminals;
}
export function subscribeTerminal(ws: WsClient, id: string,
  onData: (bytes: Uint8Array) => void, onExit: () => void): () => void {
  const dataCb = (p: any) => {
    const bin = atob(p.data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    onData(bytes);
  };
  const exitCb = () => onExit();
  ws.on(`terminal.data.${id}`, dataCb);
  ws.on(`terminal.exit.${id}`, exitCb);
  return () => { ws.off(`terminal.data.${id}`, dataCb); ws.off(`terminal.exit.${id}`, exitCb); };
}
