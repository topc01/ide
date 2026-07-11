import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    render(<NewSessionModal />);
    expect(screen.queryByText("Nueva sesión")).not.toBeInTheDocument();
  });

  it("Crear deshabilitado sin nombre; se habilita al escribir", async () => {
    const user = userEvent.setup();
    render(<NewSessionModal />);
    const crear = screen.getByRole("button", { name: "Crear" }) as HTMLButtonElement;
    expect(crear).toBeDisabled();
    await user.type(screen.getByLabelText("Nombre"), "Feature X");
    expect(crear).not.toBeDisabled();
  });

  it("crear coordinadora llama createSession con parentId", async () => {
    const user = userEvent.setup();
    const { createSession } = await import("../../transport/sessions");
    render(<NewSessionModal />);
    await user.type(screen.getByLabelText("Nombre"), "Coord");
    await user.click(screen.getByRole("button", { name: "Crear" }));
    expect(createSession).toHaveBeenCalledWith(expect.anything(),
      expect.objectContaining({ name: "Coord", kind: "coordinator", parentId: null }));
  });

  it("cerrar el modal (onOpenChange) llama a la acción real de cierre", async () => {
    const user = userEvent.setup();
    render(<NewSessionModal />);
    await user.keyboard("{Escape}");
    expect(useSessions.getState().modalParentId).toBe(undefined);
  });

  it("elegir tipo 'work' revela el Repo; coordinator lo oculta", async () => {
    const user = userEvent.setup();
    render(<NewSessionModal />);
    expect(screen.queryByLabelText("Repo")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Tipo" }));
    await user.click(screen.getByRole("option", { name: /trabajo/i }));
    expect(screen.getByLabelText("Repo")).toBeInTheDocument();
  });
});
