import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SessionNodeRow } from "./SessionNodeRow";
import { useSessions } from "../../state/sessions";

vi.mock("../../transport/sessions", async (orig) => ({
  ...(await orig<any>()),
  renameSession: vi.fn().mockResolvedValue({ renamed: true }),
}));
vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));

const node = { id: "n1", name: "Viejo", status: "idle", expanded: true, children: [] };

describe("rename inline", () => {
  beforeEach(() => useSessions.setState({
    tree: [node as any], repos: [], activeSessionId: null, editingId: null, modalParentId: undefined }));

  it("doble-click abre input; Esc cancela", () => {
    render(<SessionNodeRow node={node as any} depth={0} />);
    fireEvent.doubleClick(screen.getByText("Viejo"));
    const input = screen.getByDisplayValue("Viejo") as HTMLInputElement;
    fireEvent.keyDown(input, { key: "Escape" });
    expect(useSessions.getState().editingId).toBe(null);
  });

  it("Enter confirma con renameSession", async () => {
    const { renameSession } = await import("../../transport/sessions");
    render(<SessionNodeRow node={node as any} depth={0} />);
    fireEvent.doubleClick(screen.getByText("Viejo"));
    const input = screen.getByDisplayValue("Viejo");
    fireEvent.change(input, { target: { value: "Nuevo" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(renameSession).toHaveBeenCalledWith(expect.anything(), "n1", "Nuevo");
  });
});
