import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useNotion } from "../../state/notion";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const load = vi.fn(), add = vi.fn(), remove = vi.fn();
import { NotionPanel } from "./NotionPanel";

function setState(over: any) {
  useNotion.setState({ connected: true, pages: [], loading: false, error: null, load, add, remove, ...over });
}
beforeEach(() => {
  load.mockReset(); add.mockReset();
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  setState({});
});

describe("NotionPanel", () => {
  it("sin conexión muestra 'conectá Notion'", () => {
    setState({ connected: false });
    render(<NotionPanel />);
    expect(screen.getByText(/conectá notion/i)).toBeInTheDocument();
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
