import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useSettings } from "../../state/settings";
import { SettingsModal } from "./SettingsModal";

const items = [
  { key: "overview", title: "Overview", description: "resumen", count: 0, rows: [] },
  { key: "roles", title: "Roles", description: "roles del ws", count: 2,
    rows: [{ label: "arquitecto", inUse: true }, { label: "lector", inUse: false }] },
];
beforeEach(() => useSettings.setState({ items: items as any, open: true, selectedKey: "roles" }));

describe("SettingsModal", () => {
  it("muestra el item seleccionado con filas y badge en uso", () => {
    render(<SettingsModal />);
    expect(screen.getByText("roles del ws")).toBeInTheDocument();
    expect(screen.getByText("arquitecto")).toBeInTheDocument();
    const row = screen.getByText("arquitecto").closest("[data-row]") as HTMLElement;
    expect(row.textContent).toMatch(/en uso/i);
  });
  it("clickear otro item del nav lo selecciona", () => {
    render(<SettingsModal />);
    fireEvent.click(screen.getByRole("button", { name: /Overview/i }));
    expect(useSettings.getState().selectedKey).toBe("overview");
    expect(screen.getByText("resumen")).toBeInTheDocument();
  });
});
