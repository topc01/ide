import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SquareTerminal, Search } from "lucide-react";
import { registerModule } from "../modules/registry";
import { useFolders } from "../state/folders";
import { ActionMenu } from "./ActionMenu";

registerModule({ id: "terminal", title: "Terminal", icon: SquareTerminal, Panel: () => null });
registerModule({ id: "search", title: "Buscar", icon: Search, Panel: () => null });

describe("ActionMenu filtrado", () => {
  it("muestra solo los módulos de [ui] modules", () => {
    useFolders.setState({ uiModules: ["sessions", "terminal"] });
    render(<ActionMenu />);
    expect(screen.getByLabelText("Terminal")).toBeInTheDocument();
    expect(screen.queryByLabelText("Buscar")).not.toBeInTheDocument();
  });
});
