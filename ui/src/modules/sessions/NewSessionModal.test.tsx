import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useSessions } from "../../state/sessions";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/sessions", async (orig) => ({
  ...(await orig<any>()),
  createSession: vi.fn().mockResolvedValue({ session: { id: "x", name: "N", status: "idle", children: [] } }),
  fetchTree: vi.fn().mockResolvedValue({ sessions: [], repos: [] }),
}));

import { NewSessionModal } from "./NewSessionModal";

describe("NewSessionModal", () => {
  beforeEach(() => useSessions.setState({
    tree: [], repos: [{ id: "repoA", name: "repoA", branch: "main" }],
    activeSessionId: null, editingId: null, modalParentId: null }));

  it("no renderiza si el modal está cerrado", () => {
    useSessions.setState({ modalParentId: undefined });
    const { container } = render(<NewSessionModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it("Crear deshabilitado sin nombre; se habilita al escribir", () => {
    render(<NewSessionModal />);
    const crear = screen.getByRole("button", { name: "Crear" }) as HTMLButtonElement;
    expect(crear.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Feature X" } });
    expect(crear.disabled).toBe(false);
  });

  it("Crear coordinadora llama createSession con parentId", async () => {
    const { createSession } = await import("../../transport/sessions");
    render(<NewSessionModal />);
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Coord" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(createSession).toHaveBeenCalledWith(expect.anything(),
      expect.objectContaining({ name: "Coord", kind: "coordinator", parentId: null }));
  });
});
