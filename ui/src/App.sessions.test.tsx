import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("./transport/wsClient", () => ({
  getWs: () => ({ on: () => {}, off: () => {}, onClose: () => {},
                  request: () => Promise.resolve({ modules: ["sessions", "terminal"] }) }),
}));
vi.mock("./transport/folderSessions", async (orig) => ({
  ...(await orig<any>()),
  fetchSessions: vi.fn().mockResolvedValue({ workspaceRepos: [], scripts: {}, sessions: [
    { id: "fin-9", kind: "ticket", path: "", created: "1", permissions: "analyze", title: "MiTicket",
      status: "analyzing", meta: {}, repos: [], error: null, process: "stopped", terminalId: null }] }),
}));

import App from "./App";

describe("App con sesiones-carpeta", () => {
  it("monta el sidebar nuevo", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("MiTicket")).toBeInTheDocument());
  });
});
