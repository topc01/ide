import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "../modules/search/register";
import { useStore } from "../state/store";
import { InnerSidebar } from "./InnerSidebar";
import { MainPanel } from "./MainPanel";

describe("panels", () => {
  beforeEach(() => useStore.setState({ activePanel: "search", openTabs: [], activeTabId: "chat" }));
  it("InnerSidebar renderiza el Panel del módulo activo", () => {
    render(<InnerSidebar />);
    expect(screen.getByPlaceholderText(/Buscar contenido/i)).toBeInTheDocument();
  });
  it("MainPanel renderiza ChatView cuando no hay sesión activa", () => {
    render(<MainPanel />);
    expect(screen.getByText(/Selecciona una sesión para chatear\./i)).toBeInTheDocument();
  });
});
