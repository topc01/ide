import { describe, it, expect, vi, beforeEach } from "vitest";

const listTasks = vi.fn(), createTask = vi.fn();
vi.mock("../transport/tasksChannel", () => ({
  listTasks: (...a: any[]) => listTasks(...a),
  createTask: (...a: any[]) => createTask(...a),
}));
vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
import { useTasks } from "./tasks";

beforeEach(() => { listTasks.mockReset(); createTask.mockReset(); useTasks.setState({ tasks: [], error: null }); });

describe("useTasks", () => {
  it("load puebla tasks", async () => {
    listTasks.mockResolvedValue([{ id: "a", title: "A", status: null }]);
    await useTasks.getState().load();
    expect(useTasks.getState().tasks).toEqual([{ id: "a", title: "A", status: null }]);
  });
  it("create refresca la lista y devuelve el ref", async () => {
    createTask.mockResolvedValue({ id: "x", title: "X", status: "todo" });
    listTasks.mockResolvedValue([{ id: "x", title: "X", status: "todo" }]);
    const ref = await useTasks.getState().create("X");
    expect(ref!.id).toBe("x");
    expect(useTasks.getState().tasks).toHaveLength(1);
  });
  it("create con fallo setea error y no propaga (devuelve undefined)", async () => {
    createTask.mockRejectedValue(new Error("boom"));
    const ref = await useTasks.getState().create("X");
    expect(ref).toBeUndefined();
    expect(useTasks.getState().error).toBe("boom");
  });
});
