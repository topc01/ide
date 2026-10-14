import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { useFolders } from "../state/folders";

const wsListeners: Record<string, (p: any) => void> = {};
vi.mock("../transport/wsClient", () => ({
  getWs: () => ({ on: (c: string, cb: any) => { wsListeners[c] = cb; }, off: () => {} }) }));
const fetchDoc = vi.fn().mockResolvedValue({ name: "TICKET.md", text: "---\nstatus: ready\n---\n## Scope\nX" });
const openSession = vi.fn().mockResolvedValue({ process: "running" });
const refreshReview = vi.fn().mockResolvedValue({});
vi.mock("../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()),
  openSession: (...a: any[]) => openSession(...a),
  refreshReview: (...a: any[]) => refreshReview(...a),
  fetchDoc: (...a: any[]) => fetchDoc(...a),
}));
vi.mock("./TerminalTab", () => ({ TerminalTab: ({ id }: { id: string }) => <div data-testid={`term-${id}`} /> }));

import { SessionView } from "./SessionView";

const base = { path: "", created: "1", permissions: "analyze", meta: {}, repos: [], error: null };
const sessions: any[] = [
  { ...base, id: "a", kind: "ticket", title: "A", status: "ready", process: "running", terminalId: "t1" },
  { ...base, id: "b", kind: "ticket", title: "B", status: null, process: "stopped", terminalId: null,
    launchError: "no se encontró `claude`" },
  { ...base, id: "r", kind: "review", title: "R", status: "reviewing", process: "stopped",
    terminalId: null, prState: "stale" },
];

describe("SessionView", () => {
  beforeEach(() => useFolders.setState({
    tree: { sessions, workspaceRepos: [], scripts: {} }, activeId: "a", scriptTabs: {} }));

  it("terminal claude + doc", async () => {
    render(<SessionView />);
    expect(screen.getByTestId("term-t1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "TICKET.md" }));
    expect(await screen.findByText(/## Scope/)).toBeInTheDocument();
  });

  it("las terminales visitadas quedan montadas al cambiar de sesión", () => {   // Review Focus 4
    const { rerender } = render(<SessionView />);
    useFolders.setState({ activeId: "b" }); rerender(<SessionView />);
    expect(screen.getByTestId("term-t1")).toBeInTheDocument();
    expect(screen.getByTestId("term-t1").closest("[hidden]")).not.toBeNull();
  });

  it("parada: botón Abrir y launchError", async () => {
    useFolders.setState({ activeId: "b" });
    render(<SessionView />);
    expect(screen.getByText(/no se encontró/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    await waitFor(() => expect(openSession).toHaveBeenCalledWith(expect.anything(), "b"));
  });

  it("revisión stale ofrece refrescar", async () => {
    useFolders.setState({ activeId: "r" });
    render(<SessionView />);
    fireEvent.click(screen.getByRole("button", { name: "Refrescar" }));
    await waitFor(() => expect(refreshReview).toHaveBeenCalledWith(expect.anything(), "r"));
  });

  it("tabs de scripts", () => {
    useFolders.setState({ scriptTabs: { a: [{ terminalId: "t7", label: "repo-a:run" }] } });
    render(<SessionView />);
    fireEvent.click(screen.getByRole("tab", { name: "repo-a:run" }));
    expect(screen.getByTestId("term-t7")).toBeInTheDocument();
  });

  it("el doc limpia el error al recargar bien", async () => {
    fetchDoc.mockRejectedValueOnce({ message: "no se pudo leer" });
    render(<SessionView />);
    fireEvent.click(screen.getByRole("tab", { name: "TICKET.md" }));
    expect(await screen.findByText("no se pudo leer")).toBeInTheDocument();
    await act(async () => { wsListeners["sessions.changed"]({}); });
    expect(await screen.findByText(/## Scope/)).toBeInTheDocument();
    expect(screen.queryByText("no se pudo leer")).not.toBeInTheDocument();
  });
});
