import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const openTab = vi.fn();
vi.mock("../../state/store", () => ({ useStore: (sel: any) => sel({ openTab }) }));
const load = vi.fn(), create = vi.fn();
let state = { tasks: [] as any[], error: null as string | null, load, create };
vi.mock("../../state/tasks", () => ({ useTasks: () => state }));
import { TasksPanel } from "./TasksPanel";

beforeEach(() => { openTab.mockReset(); load.mockReset(); create.mockReset();
  state = { tasks: [{ id: "a", title: "Alpha", status: "doing" }], error: null, load, create }; });

describe("TasksPanel", () => {
  it("lista tareas y abre un tab al click", () => {
    render(<TasksPanel />);
    fireEvent.click(screen.getByText("Alpha"));
    expect(openTab).toHaveBeenCalledWith({ id: "task:a", type: "task", label: "Alpha" });
  });
  it("+ nueva crea y abre el tab", async () => {
    create.mockResolvedValue({ id: "x", title: "X", status: "todo" });
    render(<TasksPanel />);
    fireEvent.click(screen.getByText("Nueva"));
    const input = screen.getByPlaceholderText(/nombre/i);
    fireEvent.change(input, { target: { value: "X" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => expect(create).toHaveBeenCalledWith("X"));
    await vi.waitFor(() => expect(openTab).toHaveBeenCalledWith({ id: "task:x", type: "task", label: "X" }));
  });
});
