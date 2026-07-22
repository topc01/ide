import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useModels } from "../../state/models";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const downloadModel = vi.fn();
const deleteModel = vi.fn().mockResolvedValue({});
vi.mock("../../transport/modelsChannel", () => ({
  fetchModels: () => Promise.resolve({ curated: [], installed: [], inUse: null, active: {} }),
  subscribeModels: () => () => {},
  downloadModel: (...a: any[]) => downloadModel(...a),
  deleteModel: (...a: any[]) => deleteModel(...a),
}));
import { ModelsPanel } from "./ModelsPanel";

beforeEach(() => {
  downloadModel.mockClear();
  useModels.setState({
    curated: [{ repoId: "mlx-community/A", label: "Modelo A", params: "3B", quant: "4bit", sizeGb: 1.7 }],
    installed: [{ repoId: "mlx-community/B", sizeOnDisk: 2_000_000_000 }],
    inUse: "mlx-community/B", downloads: {},
  });
});

describe("ModelsPanel", () => {
  it("lista catálogo e instalados con badge en uso", () => {
    render(<ModelsPanel />);
    expect(screen.getByText("Modelo A")).toBeInTheDocument();
    expect(screen.getByText("mlx-community/B")).toBeInTheDocument();
    const row = screen.getByText("mlx-community/B").closest("[data-installed]") as HTMLElement;
    expect(row.textContent).toMatch(/en uso/i);
  });
  it("clickear Descargar dispara downloadModel con el repoId", () => {
    render(<ModelsPanel />);
    fireEvent.click(screen.getByText("Descargar", { selector: "[data-download]" }));
    expect(downloadModel).toHaveBeenCalledWith({}, "mlx-community/A");
  });
  it("una descarga activa muestra su porcentaje", () => {
    useModels.setState({ downloads: { "mlx-community/A": { downloaded: 50, total: 100 } } });
    render(<ModelsPanel />);
    expect(screen.getByText("50%")).toBeInTheDocument();
  });
});
