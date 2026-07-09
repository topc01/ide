import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useSessions } from "../../state/sessions";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/sessions", async (orig) => ({
  ...(await orig<any>()),
  createSession: vi.fn().mockResolvedValue({ session: { id: "x", name: "N", status: "idle", children: [] } }),
  fetchTree: vi.fn().mockResolvedValue({ sessions: [], repos: [] }),
  fetchBranches: vi.fn().mockResolvedValue([
    { name: "main", occupied: true }, { name: "dev", occupied: false }]),
}));

import { NewSessionModal } from "./NewSessionModal";

describe("NewSessionModal branch picker", () => {
  beforeEach(() => useSessions.setState({
    tree: [], repos: [{ id: "repoA", name: "repoA", branch: "main" }],
    activeSessionId: null, editingId: null, modalParentId: null }));

  it("al elegir 'existente' lista branches y marca ocupadas", async () => {
    render(<NewSessionModal />);
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "work" } });
    fireEvent.click(screen.getByRole("radio", { name: /existente/i }));
    await waitFor(() => screen.getByLabelText("Branch existente"));
    expect(screen.getByText(/main · ocupada/i)).toBeInTheDocument();
    expect(screen.getByText("dev")).toBeInTheDocument();
  });

  it("con acceso 'ro' la branch ocupada 'main' NO está deshabilitada", async () => {
    render(<NewSessionModal />);
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "work" } });
    fireEvent.click(screen.getByRole("radio", { name: /existente/i }));
    await waitFor(() => screen.getByLabelText("Branch existente"));
    fireEvent.change(screen.getByLabelText("Acceso"), { target: { value: "ro" } });
    const mainOption = screen.getByRole("option", { name: /main/i }) as HTMLOptionElement;
    expect(mainOption.disabled).toBe(false);
  });

  it("Crear deshabilitado si branchMode=existing sin branch elegida; se habilita al elegir", async () => {
    render(<NewSessionModal />);
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Feature X" } });
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "work" } });
    fireEvent.click(screen.getByRole("radio", { name: /existente/i }));
    await waitFor(() => screen.getByLabelText("Branch existente"));
    const crear = screen.getByRole("button", { name: "Crear" }) as HTMLButtonElement;
    expect(crear.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Branch existente"), { target: { value: "dev" } });
    expect(crear.disabled).toBe(false);
  });
});
