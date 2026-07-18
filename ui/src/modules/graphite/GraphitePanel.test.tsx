import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useGraphite } from "../../state/graphite";
import { useSessions } from "../../state/sessions";
import { useStore } from "../../state/store";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const toggleBranch = vi.fn();
const toggleCommit = vi.fn();
const restack = vi.fn();
const load = vi.fn();
import { GraphitePanel } from "./GraphitePanel";

function setGraphite(over: Partial<ReturnType<typeof useGraphite.getState>>) {
  useGraphite.setState({
    stack: [], current: null, commitsByBranch: {}, expandedBranches: [],
    expandedCommits: [], loading: false, error: null, restacking: null,
    load, toggleBranch, toggleCommit, restack, ...over,
  });
}

beforeEach(() => {
  load.mockReset(); toggleBranch.mockReset(); toggleCommit.mockReset(); restack.mockReset();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useStore.setState({ openTabs: [], activeTabId: "chat" } as any);
  setGraphite({});
});

describe("GraphitePanel", () => {
  it("sin sesión muestra estado neutro y no carga", () => {
    useSessions.setState({ activeSessionId: null } as any);
    setGraphite({});
    render(<GraphitePanel />);
    expect(screen.getByText(/seleccioná una sesión/i)).toBeInTheDocument();
    expect(load).not.toHaveBeenCalled();
  });

  it("renderiza el stack y togglea la branch al clickear", () => {
    setGraphite({ stack: [
      { name: "main", parent: null, isTrunk: true, current: false, needsRestack: false, revision: "r0" },
      { name: "feat-a", parent: "main", isTrunk: false, current: true, needsRestack: false, revision: "r1" },
    ], current: "feat-a" });
    render(<GraphitePanel />);
    expect(screen.getByText("main")).toBeInTheDocument();
    fireEvent.click(screen.getByText("feat-a"));
    expect(toggleBranch).toHaveBeenCalledWith("s1", "feat-a");
  });

  it("needsRestack muestra flecha y pide confirmación antes de restackear", () => {
    setGraphite({ stack: [
      { name: "feat-a", parent: "main", isTrunk: false, current: false, needsRestack: true, revision: "r1" },
    ] });
    render(<GraphitePanel />);
    fireEvent.click(screen.getByLabelText("restack feat-a"));
    // aparece confirmación, aún no restackea
    expect(restack).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("sí"));
    expect(restack).toHaveBeenCalledWith("s1", "feat-a");
  });

  it("expande commits→archivos y abre tab de diff al clickear un archivo", () => {
    setGraphite({
      stack: [{ name: "feat-a", parent: "main", isTrunk: false, current: false, needsRestack: false, revision: "r1" }],
      expandedBranches: ["feat-a"],
      commitsByBranch: { "feat-a": [{ hash: "abc123", message: "msg", files: [
        { path: "src/a.py", status: "M", added: 3, removed: 1 }] }] },
      expandedCommits: ["abc123"],
    });
    render(<GraphitePanel />);
    fireEvent.click(screen.getByText("src/a.py"));
    const tab = useStore.getState().openTabs[0];
    expect(tab).toMatchObject({ id: "diff:s1:@abc123:src/a.py", type: "file", label: "a.py" });
  });

  it("muestra 'desconectado' en error", () => {
    setGraphite({ error: "no es repo Graphite" });
    render(<GraphitePanel />);
    expect(screen.getByText(/desconectado/i)).toBeInTheDocument();
  });
});
