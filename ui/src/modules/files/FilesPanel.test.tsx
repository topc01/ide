import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const listFiles = vi.fn();
const openFile = vi.fn().mockResolvedValue({ id: "t1", cwd: "/x" });
vi.mock("../../transport/filesChannel", () => ({
  listFiles: (...a: any[]) => listFiles(...a),
  openFile: (...a: any[]) => openFile(...a),
}));
import { FilesPanel } from "./FilesPanel";

beforeEach(() => {
  listFiles.mockReset().mockResolvedValue({ entries: [
    { name: "src", type: "dir" }, { name: "a.txt", type: "file" }] });
  openFile.mockClear();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
});

describe("FilesPanel", () => {
  it("lista la raíz de la sesión activa", async () => {
    render(<FilesPanel />);
    await waitFor(() => expect(screen.getByText("src")).toBeInTheDocument());
    expect(screen.getByText("a.txt")).toBeInTheDocument();
  });
  it("click en carpeta pide sus hijos", async () => {
    render(<FilesPanel />);
    await waitFor(() => screen.getByText("src"));
    listFiles.mockResolvedValueOnce({ entries: [{ name: "b.py", type: "file" }] });
    fireEvent.click(screen.getByText("src"));
    await waitFor(() => expect(screen.getByText("b.py")).toBeInTheDocument());
    expect(listFiles).toHaveBeenCalledWith({}, "s1", "src");
  });
  it("click en archivo lo abre en un tab de terminal", async () => {
    render(<FilesPanel />);
    await waitFor(() => screen.getByText("a.txt"));
    fireEvent.click(screen.getByText("a.txt"));
    expect(openFile).toHaveBeenCalledWith({}, "s1", "a.txt");
    await waitFor(() => expect(useStore.getState().openTabs.some((t) => t.id === "t1")).toBe(true));
  });
  it("sin sesión muestra un mensaje", () => {
    useSessions.setState({ activeSessionId: null } as any);
    render(<FilesPanel />);
    expect(screen.getByText(/Seleccioná una sesión/i)).toBeInTheDocument();
  });
});
