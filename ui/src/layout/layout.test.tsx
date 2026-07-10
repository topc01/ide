// ui/src/layout/layout.test.tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "../modules/stubs";
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
});
