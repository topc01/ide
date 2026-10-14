import type { WsClient } from "./ws";

export interface Row { label: string; inUse: boolean }
export interface Item { key: string; title: string; description: string; count: number; rows: Row[] }

export async function fetchCustomizations(ws: WsClient): Promise<Item[]> {
  return (await ws.request("customizations.list", {})).items ?? [];
}
