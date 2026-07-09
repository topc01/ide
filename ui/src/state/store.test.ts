import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

describe("store", () => {
  beforeEach(() => useStore.setState({ repos: [], activePanel: "sessions", openTabs: [], activeTabId: "chat" }));
  it("setRepos", () => { useStore.getState().setRepos([{ id: "a", name: "a", branch: "main" }]);
    expect(useStore.getState().repos).toHaveLength(1); });
  it("open/close tab cae a chat", () => {
    const s = useStore.getState();
    s.openTab({ id: "t1", type: "file", label: "f" });
    expect(useStore.getState().activeTabId).toBe("t1");
    useStore.getState().closeTab("t1");
    expect(useStore.getState().activeTabId).toBe("chat");
  });
});
