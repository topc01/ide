import type { WsClient } from "./ws";

export function openTerminal(ws: WsClient,
  opts: { sessionId?: string; repoId?: string; cmd?: string[] }): Promise<{ id: string; cwd: string }> {
  return ws.request("terminal.open", opts);
}
export function writeTerminal(ws: WsClient, id: string, data: string): Promise<any> {
  return ws.request("terminal.write", { id, data: btoa(data) });
}
export function resizeTerminal(ws: WsClient, id: string, cols: number, rows: number): Promise<any> {
  return ws.request("terminal.resize", { id, cols, rows });
}
export function closeTerminal(ws: WsClient, id: string): Promise<any> {
  return ws.request("terminal.close", { id });
}
export function subscribeTerminal(ws: WsClient, id: string,
  onData: (bytes: Uint8Array) => void, onExit: () => void): void {
  ws.on(`terminal.data.${id}`, (p: any) => {
    const bin = atob(p.data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    onData(bytes);
  });
  ws.on(`terminal.exit.${id}`, () => onExit());
}
