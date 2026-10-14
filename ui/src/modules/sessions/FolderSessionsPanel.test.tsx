// ui/src/modules/sessions/FolderSessionsPanel.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { useFolders } from "../../state/folders";

const listeners: Record<string, (p: any) => void> = {};
const closeCbs: (() => void)[] = [];
vi.mock("../../transport/wsClient", () => ({
  getWs: () => ({ on: (c: string, cb: any) => { listeners[c] = cb; }, off: () => {},
                  onClose: (cb: any) => closeCbs.push(cb) }),
}));
const tree = {
  workspaceRepos: [{ id: "repo-a", name: "repo-a", branch: "main" }],
  scripts: { "repo-a": [{ name: "run", executable: true }, { name: "test", executable: false }] },
  sessions: [
    { id: "s-main1", kind: "main", path: "", created: "1", permissions: "full", title: null, status: null,
      meta: {}, repos: [], error: null, process: "running", terminalId: "t0" },
    { id: "fin-1", kind: "ticket", path: "", created: "2", permissions: "analyze", title: "Exportar",
      status: "ready", meta: {}, error: null, process: "stopped", terminalId: null,
      repos: [{ name: "repo-a", state: "ok", branch: "fin-1", port: 8100, setup: "failed" }] },
    { id: "fin-2", kind: "ticket", path: "", created: "3", permissions: "analyze", title: "Roto",
      status: null, meta: {}, error: "TICKET.md: línea 2 inválida", process: "queued",
      terminalId: null,
      repos: [{ name: "repo-a", state: "missing", branch: null, port: null, setup: null }] },
    { id: "pr-repo-a-4", kind: "review", path: "", created: "4", permissions: "analyze",
      title: "Refactor auth", status: "reviewing", meta: { author: "@juan" }, repos: [], error: null,
      process: "stopped", terminalId: null, prState: "stale", pollError: null },
    { id: "pr-repo-a-5", kind: "review", path: "", created: "5", permissions: "analyze",
      title: "Otro PR", status: "reviewing", meta: {}, repos: [], error: null,
      process: "running", terminalId: "t9", prState: null, pollError: "gh: 502",
      lastOk: "2026-10-13T10:00:00", attention: "trust" },
  ],
};
const fetchSessions = vi.fn().mockResolvedValue(tree);
const runScript = vi.fn().mockResolvedValue({ terminalId: "t5" });
const rmRepo = vi.fn().mockResolvedValue({ ok: true });
const stopSession = vi.fn().mockRejectedValue({ code: "x", message: "no se pudo parar" });
const newSession = vi.fn().mockRejectedValue({ code: "main_exists", message: "ya existe la principal" });
vi.mock("../../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()), fetchSessions: (...a: any[]) => fetchSessions(...a),
  runScript: (...a: any[]) => runScript(...a), rmRepo: (...a: any[]) => rmRepo(...a),
  stopSession: (...a: any[]) => stopSession(...a), newSession: (...a: any[]) => newSession(...a),
}));

import { FolderSessionsPanel } from "./FolderSessionsPanel";

describe("FolderSessionsPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    useFolders.setState({ groupBy: "none", activeId: null, scriptTabs: {}, connected: true, modal: null });
  });

  it("principal primero, sesiones, y revisiones aparte", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    expect(screen.getByText("s-main1")).toBeInTheDocument();
    expect(screen.getByText("Revisiones")).toBeInTheDocument();
    expect(screen.getByText("Refactor auth")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("@juan")).toBeInTheDocument();
    expect(screen.getByLabelText("en cola")).toBeInTheDocument();
    expect(screen.getByTitle("TICKET.md: línea 2 inválida")).toBeInTheDocument();
  });

  it("agrupar por estado desde el botón y persistir", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    fireEvent.click(screen.getByLabelText("Agrupar"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Por estado" }));
    expect(screen.getByText("Necesitan tu atención")).toBeInTheDocument();
    expect(screen.getByText("En cola")).toBeInTheDocument();
    expect(localStorage.getItem("ide.groupBy")).toBe("status");
  });

  it("repo con setup fallido y menú de scripts", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    fireEvent.click(screen.getByText("Exportar"));
    expect(useFolders.getState().activeId).toBe("fin-1");
    expect(screen.getByText("✗ setup")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Scripts de repo-a"));
    expect(screen.getByRole("menuitem", { name: /test/ })).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(screen.getByRole("menuitem", { name: /run/ }));
    await waitFor(() => expect(runScript).toHaveBeenCalledWith(expect.anything(), "fin-1", "repo-a", "run"));
    expect(useFolders.getState().scriptTabs["fin-1"]).toEqual([{ terminalId: "t5", label: "repo-a:run" }]);
  });

  it("repo missing ofrece quitar", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Roto"));
    fireEvent.click(screen.getByRole("button", { name: "quitar" }));
    await waitFor(() => expect(rmRepo).toHaveBeenCalledWith(expect.anything(), "fin-2", "repo-a"));
  });

  it("evento sessions.changed actualiza y el cierre del WS muestra desconectado", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    act(() => listeners["sessions.changed"]({ ...tree, sessions: tree.sessions.slice(0, 1) }));
    expect(screen.queryByText("Exportar")).not.toBeInTheDocument();
    act(() => closeCbs.forEach((cb) => cb()));
    expect(screen.getByText(/desconectado/i)).toBeInTheDocument();
  });

  it("badge de confiar carpeta y título del poll con último OK", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Otro PR"));
    expect(screen.getByText("⚠ confiar carpeta")).toHaveAttribute("title",
      "Claude Code pide confirmar la carpeta: abre la terminal y acepta");
    expect(screen.getByText("⚠ poll")).toHaveAttribute("title",
      expect.stringContaining("último OK: 2026-10-13T10:00:00"));
  });

  it("error al parar se muestra", async () => {
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Otro PR"));
    fireEvent.click(screen.getByLabelText("Parar pr-repo-a-5"));
    expect(await screen.findByTitle("no se pudo parar")).toBeInTheDocument();
  });

  it("error al crear la principal se muestra", async () => {
    fetchSessions.mockResolvedValueOnce({ ...tree, sessions: tree.sessions.slice(1) });
    render(<FolderSessionsPanel />);
    await waitFor(() => screen.getByText("Exportar"));
    fireEvent.click(screen.getByText("Principal"));
    expect(await screen.findByTitle("ya existe la principal")).toBeInTheDocument();
  });
});
