import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("./transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("./transport/sessions", async (orig) => ({
  ...(await orig<any>()),
  fetchTree: vi.fn().mockResolvedValue({
    sessions: [{ id: "s1", name: "MiSesión", status: "idle", expanded: true, children: [] }],
    repos: [{ id: "repoA", name: "repoA", branch: "main" }],
  }),
}));

import App from "./App";

describe("App con sesiones", () => {
  it("monta el SessionsPanel con el árbol del backend", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("MiSesión")).toBeInTheDocument());
    expect(screen.getByText(/Agregar sesión/i)).toBeInTheDocument();
  });
});
