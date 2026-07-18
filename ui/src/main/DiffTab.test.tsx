import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchDiff = vi.fn();
vi.mock("../transport/changesChannel", () => ({ fetchDiff: (...a: any[]) => fetchDiff(...a) }));
import { DiffTab } from "./DiffTab";

beforeEach(() => { fetchDiff.mockReset(); });

describe("DiffTab", () => {
  it("parsea el id y renderiza líneas add/del/ctx", async () => {
    fetchDiff.mockResolvedValue([
      { type: "ctx", text: "uno" },
      { type: "del", text: "viejo" },
      { type: "add", text: "nuevo" },
    ]);
    render(<DiffTab id="diff:s1:M:src/a.py" />);
    await waitFor(() => screen.getByText("nuevo"));
    expect(screen.getByText("viejo")).toBeInTheDocument();
    expect(fetchDiff).toHaveBeenCalledWith({}, { sessionId: "s1", path: "src/a.py", status: "M" });
    expect(screen.getByText("src/a.py")).toBeInTheDocument();
  });

  it("muestra error si el diff falla", async () => {
    fetchDiff.mockRejectedValue({ message: "no es repo git" });
    render(<DiffTab id="diff:s1:M:src/a.py" />);
    await waitFor(() => screen.getByText(/no se pudo leer el diff/i));
  });
});
