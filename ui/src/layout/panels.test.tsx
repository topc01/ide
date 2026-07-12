import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "../modules/stubs";
import { useStore } from "../state/store";
import { ContextPanel } from "./ContextPanel";
import { MainPanel } from "./MainPanel";

describe("panels", () => {
  beforeEach(() => useStore.setState({ activePanel: "search", openTabs: [], activeTabId: "chat" }));
  it("ContextPanel renderiza el Panel del módulo activo", () => {
    render(<ContextPanel />);
    expect(screen.getByText(/Search — próximamente/i)).toBeInTheDocument();
  });
  it("MainPanel renderiza ChatView cuando no hay sesión activa", () => {
    render(<MainPanel />);
    expect(screen.getByText(/Seleccioná una sesión para chatear\./i)).toBeInTheDocument();
  });
});
