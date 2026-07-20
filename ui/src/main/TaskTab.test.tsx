import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const readTask = vi.fn(), saveTask = vi.fn();
vi.mock("../transport/tasksChannel", () => ({
  readTask: (...a: any[]) => readTask(...a),
  saveTask: (...a: any[]) => saveTask(...a),
}));
vi.mock("../state/tasks", () => ({ useTasks: (sel: any) => sel({ load: vi.fn() }) }));
import { TaskTab } from "./TaskTab";

beforeEach(() => { readTask.mockReset(); saveTask.mockReset(); vi.useFakeTimers(); });

describe("TaskTab", () => {
  it("carga el markdown y guarda con debounce al editar", async () => {
    readTask.mockResolvedValue({ id: "a", title: "Alpha", status: "todo", markdown: "# Alpha\n" });
    saveTask.mockResolvedValue({ id: "a", title: "Alpha", status: "done" });
    render(<TaskTab id="task:a" />);
    const ta = await vi.waitFor(() => screen.getByRole("textbox"));
    fireEvent.change(ta, { target: { value: "# Alpha\nstatus: done\n" } });
    await vi.advanceTimersByTimeAsync(900);
    expect(saveTask).toHaveBeenCalledWith(expect.anything(), "a", "# Alpha\nstatus: done\n");
    vi.useRealTimers();
  });
});
