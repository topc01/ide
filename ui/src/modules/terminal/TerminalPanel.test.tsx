// ui/src/modules/terminal/TerminalPanel.test.tsx
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/terminalChannel", async (orig) => ({
  ...(await orig<any>()),
  openTerminal: vi.fn().mockResolvedValue({ id: "term-1", cwd: "/wt/s1" }),
  listTerminals: vi.fn().mockResolvedValue([]),
}));

import { listTerminals } from "../../transport/terminalChannel";
import { TerminalPanel } from "./TerminalPanel";

const node = { id: "s1", name: "S1", status: "idle", worktreePath: "/wt/s1", expanded: true, children: [] };

describe("TerminalPanel", () => {
  beforeEach(() => {
    useSessions.setState({ tree: [node as any], repos: [], activeSessionId: "s1",
      editingId: null, modalParentId: undefined });
    useStore.setState({ repos: [], activePanel: "terminal", openTabs: [], activeTabId: "chat" });
  });

  it("muestra la sesión activa y su cwd", () => {
    render(<TerminalPanel />);
    expect(screen.getByText("S1")).toBeInTheDocument();
    expect(screen.getByText("/wt/s1")).toBeInTheDocument();
  });

  it("abrir terminal crea una tab de tipo terminal", async () => {
    render(<TerminalPanel />);
    fireEvent.click(screen.getByRole("button", { name: /Abrir terminal/i }));
    await waitFor(() => expect(useStore.getState().openTabs.some((t) => t.type === "terminal")).toBe(true));
    expect(useStore.getState().activeTabId).toBe("term-1");
  });

  it("lista las terminales existentes de la sesión y las abre al click", async () => {
    vi.mocked(listTerminals).mockResolvedValue([
      { id: "term-1", cmd: ["zsh"], cwd: "/wt/s1", sessionId: "s1" } as any,
    ]);
    render(<TerminalPanel />);
    await waitFor(() => expect(screen.getByText("zsh")).toBeInTheDocument());
    fireEvent.click(screen.getByText("zsh"));
    expect(useStore.getState().activeTabId).toBe("term-1");
  });
});
