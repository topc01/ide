import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionNodeRow } from "./SessionNodeRow";
import { useSessions } from "../../state/sessions";

const node = (over: any = {}) => ({
  id: "n1", name: "Coord", status: "running", role: "arquitecto",
  expanded: true, children: [{ id: "n2", name: "Hija", status: "idle", expanded: true, children: [] }],
  ...over,
});

describe("SessionNodeRow", () => {
  beforeEach(() => useSessions.setState({
    tree: [], repos: [], activeSessionId: null, editingId: null, modalParentId: undefined }));

  it("renderiza el nodo, su rol y sus hijos", () => {
    render(<SessionNodeRow node={node() as any} depth={0} />);
    expect(screen.getByText("Coord")).toBeInTheDocument();
    expect(screen.getByText("arquitecto")).toBeInTheDocument();   // pill de rol
    expect(screen.getByText("Hija")).toBeInTheDocument();          // hijo recursivo
  });

  it("indenta por profundidad (16px/nivel)", () => {
    render(<SessionNodeRow node={node({ children: [] }) as any} depth={2} />);
    const row = screen.getByText("Coord").closest("[data-session-row]") as HTMLElement;
    expect(row.style.paddingLeft).toBe("32px");   // 2 * 16
  });

  it("el status dot usa la clase de color de estado", () => {
    render(<SessionNodeRow node={node() as any} depth={0} />);
    const row = screen.getByText("Coord").closest("[data-session-row]") as HTMLElement;
    expect(row.querySelector(".bg-status-running")).not.toBeNull();
  });
});
