import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "../modules/search/register";
import { useStore } from "../state/store";
import { InnerSidebar } from "./InnerSidebar";
import { ActionMenu } from "./ActionMenu";
import { MainPanel } from "./MainPanel";

describe("panels", () => {
  beforeEach(() => useStore.setState({ activePanel: "search", openTabs: [], activeTabId: "chat", innerSidebarOpen: true }));
  it("InnerSidebar renderiza el Panel del módulo activo", () => {
    render(<InnerSidebar />);
    expect(screen.getByPlaceholderText(/Buscar contenido/i)).toBeInTheDocument();
  });
  it("el botón de arriba del ActionMenu colapsa y expande la InnerSidebar", () => {
    render(<><ActionMenu /><InnerSidebar /></>);
    const toggle = screen.getAllByRole("button")[0];
    expect(toggle).toHaveAccessibleName("Colapsar sidebar interna");
    fireEvent.click(toggle);
    expect(screen.queryByPlaceholderText(/Buscar contenido/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expandir sidebar interna" }));
    expect(screen.getByPlaceholderText(/Buscar contenido/i)).toBeInTheDocument();
  });
  it("elegir un módulo con la InnerSidebar colapsada la expande", () => {
    useStore.setState({ innerSidebarOpen: false });
    render(<><ActionMenu /><InnerSidebar /></>);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByPlaceholderText(/Buscar contenido/i)).toBeInTheDocument();
  });
  it("MainPanel renderiza ChatView cuando no hay sesión activa", () => {
    render(<MainPanel />);
    expect(screen.getByText(/Selecciona una sesión para chatear\./i)).toBeInTheDocument();
  });
});
