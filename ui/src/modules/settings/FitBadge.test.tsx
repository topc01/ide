import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FitBadge } from "./FitBadge";

const FIT = { level: "ok" as const, fitLabel: "Perfect", memoryRequiredGb: 6.7, memoryAvailableGb: 24,
  estimatedTps: 9.5, diskSizeGb: 5.8, bestQuant: "mlx-8bit", contextLength: 32768, score: 87,
  scoreComponents: { fit: 100, speed: 20, quality: 99, context: 100 } };

describe("FitBadge", () => {
  it("muestra 'entra' + tok/s para level ok", () => {
    render(<FitBadge fit={FIT} />);
    expect(screen.getByText("entra")).toBeInTheDocument();
    expect(screen.getByText(/9\.5 tok\/s/)).toBeInTheDocument();
  });
  it("toggle detalles despliega las métricas", () => {
    render(<FitBadge fit={FIT} />);
    expect(screen.queryByText(/mlx-8bit/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("detalles", { selector: "[data-fit-details]" }));
    expect(screen.getByText(/mlx-8bit/)).toBeInTheDocument();
  });
  it("sin dato (null) no renderiza nada", () => {
    const { container } = render(<FitBadge fit={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
