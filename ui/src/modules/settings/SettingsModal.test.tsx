import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useSettings } from "../../state/settings";
import { SettingsModal } from "./SettingsModal";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/modelsChannel", () => ({
  fetchModels: () => Promise.resolve({ curated: [], installed: [], inUse: null, active: {} }),
  subscribeModels: () => () => {}, downloadModel: vi.fn(), deleteModel: vi.fn(),
  getMlxConfig: () => Promise.resolve({ enabled: false, model: "", routerPrompt: "D", defaultPrompt: "D" }),
  setMlxConfig: () => Promise.resolve({}),
  fetchFit: () => Promise.resolve({}),
}));

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
  it("el nav tiene Modelos y al seleccionarlo muestra el panel", () => {
    render(<SettingsModal />);
    fireEvent.click(screen.getByRole("button", { name: /Modelos/i }));
    expect(useSettings.getState().selectedKey).toBe("models");
    expect(screen.getByText(/Descargar y gestionar/i)).toBeInTheDocument();
  });
});
