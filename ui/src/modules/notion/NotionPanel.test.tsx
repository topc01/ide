import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useNotion } from "../../state/notion";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const load = vi.fn(), add = vi.fn(), remove = vi.fn(), connect = vi.fn(), disconnect = vi.fn();
import { NotionPanel } from "./NotionPanel";

function setState(over: any) {
  useNotion.setState({ connected: true, pages: [], loading: false, error: null, load, add, remove, connect, disconnect, ...over });
}
beforeEach(() => {
  load.mockReset(); add.mockReset(); connect.mockReset(); disconnect.mockReset();
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  setState({});
});

describe("NotionPanel", () => {
  it("desconectado muestra input de token y conecta", () => {
    setState({ connected: false });
    render(<NotionPanel />);
    const input = screen.getByPlaceholderText(/secret/i);
    fireEvent.change(input, { target: { value: "tok-123" } });
    fireEvent.click(screen.getByRole("button", { name: /conectar/i }));
    expect(connect).toHaveBeenCalledWith("tok-123");
  });
  it("conectado muestra desconectar", () => {
    setState({ connected: true, pages: [] });
    render(<NotionPanel />);
    fireEvent.click(screen.getByLabelText(/desconectar/i));
    expect(disconnect).toHaveBeenCalled();
  });
  it("lista páginas y abre tab al click", () => {
    setState({ pages: [{ id: "p1", title: "Mi Página" }] });
    render(<NotionPanel />);
    fireEvent.click(screen.getByText("Mi Página"));
    expect(useStore.getState().openTabs[0]).toMatchObject({ id: "notion:p1", type: "page", label: "Mi Página" });
  });
  it("+ Nueva agrega por URL", () => {
    setState({ pages: [] });
    render(<NotionPanel />);
    fireEvent.click(screen.getByText(/nueva/i));
    fireEvent.change(screen.getByPlaceholderText(/url/i), { target: { value: "http://notion.so/x" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/url/i), { key: "Enter" });
    expect(add).toHaveBeenCalledWith("http://notion.so/x");
  });
});
