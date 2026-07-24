import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

describe("store", () => {
  beforeEach(() => useStore.setState({ repos: [], activePanel: "search", openTabs: [], activeTabId: "chat", fileTabs: {} }));
  it("setRepos", () => { useStore.getState().setRepos([{ id: "a", name: "a", branch: "main" }]);
    expect(useStore.getState().repos).toHaveLength(1); });
  it("open/close tab cae a chat", () => {
    const s = useStore.getState();
    s.openTab({ id: "t1", type: "file", label: "f" });
    expect(useStore.getState().activeTabId).toBe("t1");
    useStore.getState().closeTab("t1");
    expect(useStore.getState().activeTabId).toBe("chat");
  });
  it("noteFileTab registra y closeTab limpia el mapa archivo->tab", () => {
    const s = useStore.getState();
    s.openTab({ id: "t1", type: "terminal", label: "a.txt" });
    s.noteFileTab("s1:a.txt", "t1");
    expect(useStore.getState().fileTabs["s1:a.txt"]).toBe("t1");
    useStore.getState().closeTab("t1");
    expect(useStore.getState().fileTabs["s1:a.txt"]).toBeUndefined();   // limpiado al cerrar
  });
});
