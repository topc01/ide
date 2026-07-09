// ui/src/layout/layout.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "../modules/stubs";
import { ActivityRail } from "./ActivityRail";
import { TabStrip } from "./TabStrip";

describe("layout", () => {
  it("ActivityRail muestra un botón por módulo", () => {
    render(<ActivityRail />);
    expect(screen.getByRole("button", { name: "Terminal" })).toBeInTheDocument();
  });
  it("TabStrip tiene la pestaña Chat fija", () => {
    render(<TabStrip />);
    expect(screen.getByText("Chat")).toBeInTheDocument();
  });
});
