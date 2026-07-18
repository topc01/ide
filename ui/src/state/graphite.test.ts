import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchStack = vi.fn();
const fetchBranch = vi.fn();
const restackBranch = vi.fn();
vi.mock("../transport/graphiteChannel", () => ({
  fetchStack: (...a: any[]) => fetchStack(...a),
  fetchBranch: (...a: any[]) => fetchBranch(...a),
  restackBranch: (...a: any[]) => restackBranch(...a),
}));
import { useSessions } from "./sessions";
import { useGraphite } from "./graphite";

beforeEach(() => {
  fetchStack.mockReset(); fetchBranch.mockReset(); restackBranch.mockReset();
  useSessions.setState({ activeSessionId: "s1" } as any);
  useGraphite.setState({
    stack: [], current: null, commitsByBranch: {}, expandedBranches: [],
    expandedCommits: [], loading: false, error: null, restacking: null,
  });
});

describe("state/graphite", () => {
  it("load guarda stack/current y limpia error", async () => {
    fetchStack.mockResolvedValue({ stack: [{ name: "main" }], current: "main" });
    await useGraphite.getState().load("s1");
    expect(useGraphite.getState().stack).toEqual([{ name: "main" }]);
    expect(useGraphite.getState().current).toBe("main");
    expect(useGraphite.getState().error).toBeNull();
  });

  it("load con error limpia stack y setea error", async () => {
    useGraphite.setState({ stack: [{ name: "viejo" } as any] });
    fetchStack.mockRejectedValue({ message: "no es repo Graphite" });
    await useGraphite.getState().load("s1");
    expect(useGraphite.getState().stack).toEqual([]);
    expect(useGraphite.getState().error).toBe("no es repo Graphite");
  });

  it("toggleBranch expande y trae commits una sola vez", async () => {
    fetchBranch.mockResolvedValue([{ hash: "a", message: "m", files: [] }]);
    await useGraphite.getState().toggleBranch("s1", "feat-a");
    expect(useGraphite.getState().expandedBranches).toContain("feat-a");
    expect(useGraphite.getState().commitsByBranch["feat-a"]).toHaveLength(1);
    await useGraphite.getState().toggleBranch("s1", "feat-a");  // colapsa
    expect(useGraphite.getState().expandedBranches).not.toContain("feat-a");
    expect(fetchBranch).toHaveBeenCalledTimes(1);  // no re-fetch
  });

  it("restack actualiza el stack", async () => {
    restackBranch.mockResolvedValue({ stack: [{ name: "main" }], current: "main" });
    await useGraphite.getState().restack("s1", "feat-a");
    expect(useGraphite.getState().stack).toEqual([{ name: "main" }]);
    expect(useGraphite.getState().restacking).toBeNull();
  });
});
