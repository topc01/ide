import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { useFolders } from "../../state/folders";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const newSession = vi.fn();
vi.mock("../../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()), newSession: (...a: any[]) => newSession(...a),
}));

import { NewFolderSessionModal } from "./NewFolderSessionModal";

describe("NewFolderSessionModal", () => {
  beforeEach(() => { newSession.mockReset(); useFolders.setState({ modal: null, activeId: null }); });

  it("crea ticket con plantilla y activa la sesión", async () => {
    newSession.mockResolvedValue({ session: { id: "fin-1" }, process: "running" });
    useFolders.setState({ modal: "session" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("Id"), { target: { value: "FIN-1" } });
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Exportar" } });
    fireEvent.change(screen.getByLabelText("URL de Notion"), { target: { value: "https://n" } });
    fireEvent.change(screen.getByLabelText("Detalle"), { target: { value: "cuerpo" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    await waitFor(() => expect(useFolders.getState().activeId).toBe("fin-1"));
    expect(newSession.mock.calls[0][1]).toEqual({ id: "FIN-1", template: "ticket", title: "Exportar",
      vars: { title: "Exportar", notion_url: "https://n", body: "cuerpo" } });
    expect(useFolders.getState().modal).toBe(null);
  });

  it("sin id y con URL de Notion, el id lo deriva el server (notion)", async () => {
    newSession.mockResolvedValue({ session: { id: "n-1a2b3c4d" }, process: "running" });
    useFolders.setState({ modal: "session" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "T" } });
    fireEvent.change(screen.getByLabelText("URL de Notion"), { target: { value: " https://notion.so/x " } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    await waitFor(() => expect(newSession).toHaveBeenCalled());
    expect(newSession.mock.calls[0][1]).toMatchObject({ notion: "https://notion.so/x", template: "ticket" });
    expect(newSession.mock.calls[0][1].id).toBeUndefined();
  });

  it("muestra el error del server y no cierra", async () => {
    newSession.mockRejectedValue({ code: "session_exists", message: "ya existe la sesión fin-1" });
    useFolders.setState({ modal: "session" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ya existe");
    expect(useFolders.getState().modal).toBe("session");
  });

  it("revisión por URL", async () => {
    newSession.mockResolvedValue({ session: { id: "pr-repo-a-4" }, process: "running" });
    useFolders.setState({ modal: "review" });
    render(<NewFolderSessionModal />);
    fireEvent.change(screen.getByLabelText("URL del PR"),
      { target: { value: "https://github.com/acme/repo-a/pull/4" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    await waitFor(() => expect(newSession.mock.calls[0][1]).toEqual(
      { review: "https://github.com/acme/repo-a/pull/4" }));
  });
  it("limpia el error al reabrir el modal", async () => {
    newSession.mockRejectedValue({ code: "session_exists", message: "ya existe" });
    useFolders.setState({ modal: "session" });
    render(<NewFolderSessionModal />);
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ya existe");
    act(() => useFolders.setState({ modal: null }));
    act(() => useFolders.setState({ modal: "session" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
