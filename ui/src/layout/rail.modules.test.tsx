import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SquareTerminal, Search } from "lucide-react";
import { registerModule } from "../modules/registry";
import { useFolders } from "../state/folders";
import { ActivityRail } from "./ActivityRail";

registerModule({ id: "terminal", title: "Terminal", icon: SquareTerminal, Panel: () => null });
registerModule({ id: "search", title: "Buscar", icon: Search, Panel: () => null });

describe("ActivityRail filtrado", () => {
  it("muestra solo los módulos de [ui] modules", () => {
    useFolders.setState({ uiModules: ["sessions", "terminal"] });
    render(<ActivityRail />);
    expect(screen.getByLabelText("Terminal")).toBeInTheDocument();
    expect(screen.queryByLabelText("Buscar")).not.toBeInTheDocument();
  });
});
