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
});
