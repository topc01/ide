import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useChanges } from "../../state/changes";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const load = vi.fn();
vi.mock("../../state/changes", async (orig) => {
  const mod = await (orig() as any);
  return mod;
});
import { ChangesPanel } from "./ChangesPanel";

beforeEach(() => {
  vi.useFakeTimers();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  useChanges.setState({
    status: { name: "r", path: "/r", branch: "main", head: "h",
      files: [{ path: "src/a.py", status: "M", added: 3, removed: 1 }],
      totalAdded: 3, totalRemoved: 1 },
    loading: false, error: null, load,
  });
});

describe("ChangesPanel", () => {
  it("lista los archivos y abre una tab al clickear", () => {
    render(<ChangesPanel />);
    expect(screen.getByText("src/a.py")).toBeInTheDocument();
    fireEvent.click(screen.getByText("src/a.py"));
    const tab = useStore.getState().openTabs[0];
    expect(tab).toMatchObject({ id: "diff:s1:M:src/a.py", type: "file", label: "a.py" });
    vi.useRealTimers();
  });

  it("muestra 'desconectado' cuando hay error", () => {
    useChanges.setState({ status: null, loading: false, error: "no es repo git", load });
    render(<ChangesPanel />);
    expect(screen.getByText(/desconectado/i)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
