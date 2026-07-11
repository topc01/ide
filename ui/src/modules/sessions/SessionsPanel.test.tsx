import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { useSessions } from "../../state/sessions";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/sessions", async (orig) => ({
  ...(await orig<any>()),
  fetchTree: vi.fn().mockResolvedValue({
    sessions: [{ id: "s1", name: "Coord", status: "idle", expanded: true, children: [] }],
    repos: [{ id: "repoA", name: "repoA", branch: "main" }],
  }),
}));

import { SessionsPanel } from "./SessionsPanel";

describe("SessionsPanel", () => {
  beforeEach(() => useSessions.setState({
    tree: [], repos: [], activeSessionId: null, editingId: null, modalParentId: undefined }));

  it("hidrata repos + árbol y muestra la fila punteada", async () => {
    render(<SessionsPanel />);
    await waitFor(() => expect(screen.getByText("Coord")).toBeInTheDocument());
    expect(screen.getByText("repoA")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText(/Agregar sesión/i)).toBeInTheDocument();
  });

  it("la fila punteada abre el modal root", async () => {
    render(<SessionsPanel />);
    await waitFor(() => screen.getByText(/Agregar sesión/i));
    fireEvent.click(screen.getByText(/Agregar sesión/i));
    expect(useSessions.getState().modalParentId).toBe(null);
  });

  it("la fila '+ Agregar sesión' usa borde dashed (clase)", async () => {
    render(<SessionsPanel />);
    await waitFor(() => screen.getByText(/Agregar sesión/i));
    expect(screen.getByText(/Agregar sesión/i).className).toMatch(/border-dashed/);
  });
});
