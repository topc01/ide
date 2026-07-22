import type { WsClient } from "./ws";
import type { Catalog } from "../state/models";

export function fetchModels(ws: WsClient): Promise<Catalog> {
  return ws.request("models.list", {});
}
export function downloadModel(ws: WsClient, repoId: string): Promise<any> {
  return ws.request("models.download", { repoId });
}
export function deleteModel(ws: WsClient, repoId: string): Promise<any> {
  return ws.request("models.delete", { repoId });
}
export function subscribeModels(ws: WsClient, onEvent: (e: any) => void): () => void {
  ws.on("models.event", onEvent);
  return () => ws.off("models.event", onEvent);
}
