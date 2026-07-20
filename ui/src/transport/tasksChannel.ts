import type { WsClient } from "./ws";

export interface TaskRef { id: string; title: string; status: string | null }
export interface TaskDoc extends TaskRef { markdown: string }
export type TaskMeta = TaskRef;

export async function listTasks(ws: WsClient): Promise<TaskRef[]> {
  return (await ws.request("tasks.list", {})).tasks;
}
export async function readTask(ws: WsClient, id: string): Promise<TaskDoc> {
  return ws.request("tasks.read", { id });
}
export async function saveTask(ws: WsClient, id: string, markdown: string): Promise<TaskMeta> {
  return ws.request("tasks.save", { id, markdown });
}
export async function createTask(ws: WsClient, name: string): Promise<TaskRef> {
  return (await ws.request("tasks.create", { name })).task;
}
