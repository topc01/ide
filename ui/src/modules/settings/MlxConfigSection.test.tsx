import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useMlxConfig } from "../../state/mlxConfig";
import { useModels } from "../../state/models";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const setMlxConfig = vi.fn().mockResolvedValue({});
vi.mock("../../transport/modelsChannel", () => ({
  getMlxConfig: () => Promise.resolve({ enabled: false, model: "", routerPrompt: "D", defaultPrompt: "D" }),
  setMlxConfig: (...a: any[]) => setMlxConfig(...a),
  fetchModels: () => Promise.resolve({ curated: [], installed: [], inUse: null, active: {} }),
}));
import { MlxConfigSection } from "./MlxConfigSection";

beforeEach(() => {
  setMlxConfig.mockClear();
  useMlxConfig.setState({ enabled: true, model: "mlx-community/A", routerPrompt: "P", defaultPrompt: "D", loaded: true, error: null });
  useModels.setState({ installed: [{ repoId: "mlx-community/A", sizeOnDisk: 100 }] } as any);
});

describe("MlxConfigSection", () => {
  it("renderiza toggle, modelo y prompt", () => {
    render(<MlxConfigSection />);
    expect(screen.getByText(/Activar routing/i)).toBeInTheDocument();
    expect((screen.getByPlaceholderText("mlx-community/...") as HTMLInputElement).value).toBe("mlx-community/A");
  });
  it("restaurar default setea el prompt al defaultPrompt", () => {
    render(<MlxConfigSection />);
    fireEvent.click(screen.getByText(/restaurar default/i));
    expect(useMlxConfig.getState().routerPrompt).toBe("D");
  });
  it("Guardar llama setMlxConfig con los valores", () => {
    render(<MlxConfigSection />);
    fireEvent.click(screen.getByText("Guardar", { selector: "[data-save-config]" }));
    expect(setMlxConfig).toHaveBeenCalledWith({}, { enabled: true, model: "mlx-community/A", routerPrompt: "P" });
  });
});
