// ui/src/layout/layout.test.tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "../modules/search/register";
import "../modules/terminal/register";
import { useStore } from "../state/store";
import { ActivityRail } from "./ActivityRail";
import { TabStrip } from "./TabStrip";

describe("layout", () => {
  beforeEach(() => {
    useStore.setState({ activePanel: "search" });
  });

  it("ActivityRail muestra un botón por módulo", () => {
    render(<ActivityRail />);
    expect(screen.getByRole("button", { name: "Terminal" })).toBeInTheDocument();
  });
  it("ActivityRail marca el módulo activo con la clase de primary", () => {
    const { getByRole } = render(<ActivityRail />);
    const btn = getByRole("button", { name: "Search" });
    expect(btn.className).toContain("text-primary");   // clase Tailwind del activo
  });
  it("TabStrip tiene la pestaña Chat fija", () => {
    render(<TabStrip />);
    expect(screen.getByText("Chat")).toBeInTheDocument();
  });
  it("TabStrip cierra una tab abierta con la ×", () => {
    useStore.setState({ openTabs: [{ id: "t1", type: "terminal", label: "zsh" }], activeTabId: "t1" });
    render(<TabStrip />);
    fireEvent.click(screen.getByRole("button", { name: /cerrar zsh/i }));
    expect(useStore.getState().openTabs).toHaveLength(0);
  });
  it("TabStrip activa una tab al hacer click", () => {
    useStore.setState({ openTabs: [{ id: "t1", type: "terminal", label: "zsh" }], activeTabId: "chat" });
    render(<TabStrip />);
    fireEvent.click(screen.getByText("zsh"));
    expect(useStore.getState().activeTabId).toBe("t1");
  });
});
