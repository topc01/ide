import type { WsClient } from "./ws";
import type { Catalog } from "../state/models";
import type { MlxConfig } from "../state/mlxConfig";

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
export function getMlxConfig(ws: WsClient): Promise<MlxConfig> {
  return ws.request("mlx.config.get", {});
}
export function setMlxConfig(ws: WsClient, c: { enabled: boolean; model: string; routerPrompt: string }): Promise<any> {
  return ws.request("mlx.config.set", c);
}
