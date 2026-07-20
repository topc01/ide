import { describe, it, expect, vi } from "vitest";
import { listTasks, readTask, saveTask, createTask } from "./tasksChannel";

describe("tasksChannel", () => {
  it("listTasks", async () => {
    const tasks = [{ id: "a", title: "A", status: null }];
    const ws = { request: vi.fn().mockResolvedValue({ tasks }) } as any;
    expect(await listTasks(ws)).toBe(tasks);
    expect(ws.request).toHaveBeenCalledWith("tasks.list", {});
  });
  it("readTask", async () => {
    const doc = { id: "a", title: "A", status: null, markdown: "# A" };
    const ws = { request: vi.fn().mockResolvedValue(doc) } as any;
    expect(await readTask(ws, "a")).toBe(doc);
    expect(ws.request).toHaveBeenCalledWith("tasks.read", { id: "a" });
  });
  it("saveTask", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ id: "a", title: "A", status: "done" }) } as any;
    await saveTask(ws, "a", "# A");
    expect(ws.request).toHaveBeenCalledWith("tasks.save", { id: "a", markdown: "# A" });
  });
  it("createTask", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ task: { id: "x", title: "X", status: "todo" } }) } as any;
    expect(await createTask(ws, "X")).toEqual({ id: "x", title: "X", status: "todo" });
    expect(ws.request).toHaveBeenCalledWith("tasks.create", { name: "X" });
  });
});
