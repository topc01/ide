import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

const user = () => userEvent.setup({ pointerEventsCheck: 0 });

async function selectType(u: ReturnType<typeof userEvent.setup>, name: RegExp) {
  await u.click(screen.getByRole("combobox", { name: "Tipo" }));
  await u.click(screen.getByRole("option", { name }));
}

async function selectAccess(u: ReturnType<typeof userEvent.setup>, name: RegExp) {
  await u.click(screen.getByRole("combobox", { name: "Acceso" }));
  await u.click(screen.getByRole("option", { name }));
}

async function goExisting(u: ReturnType<typeof userEvent.setup>) {
  await selectType(u, /trabajo/i);
  await u.click(screen.getByRole("radio", { name: /existente/i }));
  await waitFor(() => screen.getByRole("combobox", { name: "Branch existente" }));
}

describe("NewSessionModal branch picker", () => {
  beforeEach(() => useSessions.setState({
    tree: [], repos: [{ id: "repoA", name: "repoA", branch: "main" }],
    activeSessionId: null, editingId: null, modalParentId: null }));

  it("al elegir 'existente' lista branches y marca ocupadas", async () => {
    const u = user();
    render(<NewSessionModal />);
    await goExisting(u);
    await u.click(screen.getByRole("combobox", { name: "Branch existente" }));
    expect(screen.getByRole("option", { name: /main · ocupada/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "dev" })).toBeInTheDocument();
  });

  it("con acceso 'ro' la branch ocupada 'main' NO está deshabilitada", async () => {
    const u = user();
    render(<NewSessionModal />);
    await goExisting(u);
    await selectAccess(u, /ro/i);
    await u.click(screen.getByRole("combobox", { name: "Branch existente" }));
    const mainOption = screen.getByRole("option", { name: /main/i });
    expect(mainOption).not.toHaveAttribute("data-disabled");
  });

  it("branch ocupada 'main' está deshabilitada para acceso 'rw' (default)", async () => {
    const u = user();
    render(<NewSessionModal />);
    await goExisting(u);
    await u.click(screen.getByRole("combobox", { name: "Branch existente" }));
    const mainOption = screen.getByRole("option", { name: /main · ocupada/i });
    expect(mainOption).toHaveAttribute("data-disabled");
  });

  it("Crear deshabilitado si branchMode=existing sin branch elegida; se habilita al elegir", async () => {
    const u = user();
    render(<NewSessionModal />);
    await u.type(screen.getByLabelText("Nombre"), "Feature X");
    await goExisting(u);
    const crear = screen.getByRole("button", { name: "Crear" }) as HTMLButtonElement;
    expect(crear).toBeDisabled();
    await u.click(screen.getByRole("combobox", { name: "Branch existente" }));
    await u.click(screen.getByRole("option", { name: "dev" }));
    expect(crear).not.toBeDisabled();
  });
});
