import type { WsClient } from "./ws";

export interface NotionRef { id: string; title: string }
export type BlockNoteDoc = any[];
export interface PageData { title: string; blocks: BlockNoteDoc; unsupportedIds: string[] }
export interface SaveResult {
  appended: { clientId: string; notionId: string }[];
  deleted: string[];
  patched: string[];
  failed: { op: string; id: string; message: string }[];
}

export async function checkHealth(ws: WsClient): Promise<boolean> {
  return (await ws.request("notion.health", {})).connected;
}
export async function fetchPages(ws: WsClient): Promise<NotionRef[]> {
  return (await ws.request("notion.list", {})).pages;
}
export async function addPage(ws: WsClient, url: string): Promise<NotionRef> {
  return (await ws.request("notion.add", { url })).page;
}
export async function removePage(ws: WsClient, id: string): Promise<void> {
  await ws.request("notion.remove", { id });
}
export async function fetchPage(ws: WsClient, id: string): Promise<PageData> {
  return ws.request("notion.page", { id });
}
export async function savePage(
  ws: WsClient, id: string, loaded: BlockNoteDoc, edited: BlockNoteDoc,
  unsupportedIds: string[], idMap: Record<string, string>,
): Promise<SaveResult> {
  return ws.request("notion.save", { pageId: id, loaded, edited, unsupportedIds, idMap });
}

export async function setTitle(ws: WsClient, id: string, title: string): Promise<void> {
  await ws.request("notion.setTitle", { pageId: id, title });
}
export async function connect(ws: WsClient, token: string): Promise<boolean> {
  return (await ws.request("notion.connect", { token })).connected;
}
export async function disconnect(ws: WsClient): Promise<void> {
  await ws.request("notion.disconnect", {});
}
