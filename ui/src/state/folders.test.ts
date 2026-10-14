import { describe, it, expect, beforeEach } from "vitest";
import { useFolders } from "./folders";
import { useSessions } from "./sessions";

describe("useFolders", () => {
  beforeEach(() => { localStorage.clear(); useFolders.setState({ groupBy: "none", activeId: null, scriptTabs: {} }); });

  it("setActive refleja en useSessions para los módulos ocultos", () => {
    useFolders.getState().setActive("fin-1");
    expect(useFolders.getState().activeId).toBe("fin-1");
    expect(useSessions.getState().activeSessionId).toBe("fin-1");
  });

  it("setGroupBy persiste en localStorage", () => {
    useFolders.getState().setGroupBy("status");
    expect(localStorage.getItem("ide.groupBy")).toBe("status");
  });

  it("script tabs por sesión", () => {
    const s = useFolders.getState();
    s.addScriptTab("a", { terminalId: "t9", label: "repo-a:run" });
    s.addScriptTab("a", { terminalId: "t9", label: "repo-a:run" });
    expect(useFolders.getState().scriptTabs.a).toHaveLength(1);
    useFolders.getState().closeScriptTab("a", "t9");
    expect(useFolders.getState().scriptTabs.a).toHaveLength(0);
  });
});
