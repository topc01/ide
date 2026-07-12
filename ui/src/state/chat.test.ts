import { describe, it, expect, beforeEach } from "vitest";
import { useChat } from "./chat";

beforeEach(() => useChat.setState({ convos: {} }));

describe("useChat.applyEvent", () => {
  it("text_delta acumula texto en un mensaje de agente", () => {
    const { applyEvent } = useChat.getState();
    applyEvent("s1", { kind: "text_delta", text: "ho" });
    applyEvent("s1", { kind: "text_delta", text: "la" });
    const msgs = useChat.getState().convos["s1"].messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0]).toMatchObject({ role: "agent", text: "hola" });
  });
  it("tool_use y edit se agregan como chips del último mensaje", () => {
    const { applyEvent } = useChat.getState();
    applyEvent("s1", { kind: "text_delta", text: "x" });
    applyEvent("s1", { kind: "tool_use", id: "t1", name: "Bash", detail: "ls" });
    applyEvent("s1", { kind: "edit", id: "e1", path: "a.py", added: 2, removed: 1 });
    expect(useChat.getState().convos["s1"].messages[0].chips).toEqual([
      { kind: "tool", name: "Bash", detail: "ls" },
      { kind: "edit", path: "a.py", added: 2, removed: 1 },
    ]);
  });
  it("usage setea tokens y done apaga streaming", () => {
    const { applyEvent } = useChat.getState();
    applyEvent("s1", { kind: "text_delta", text: "x" });
    applyEvent("s1", { kind: "usage", inputTokens: 5, outputTokens: 7, totalTokens: 12 });
    applyEvent("s1", { kind: "done", sessionId: "s9", isError: false });
    const c = useChat.getState().convos["s1"];
    expect(c.messages[0].tokens).toBe(12);
    expect(c.streaming).toBe(false);
  });
  it("permission_request y error se guardan", () => {
    const { applyEvent } = useChat.getState();
    applyEvent("s1", { kind: "permission_request", id: "p1", tool: "Write", detail: "a.py" });
    applyEvent("s1", { kind: "error", code: "boom", message: "roto" });
    const c = useChat.getState().convos["s1"];
    expect(c.permission).toEqual({ id: "p1", tool: "Write", detail: "a.py" });
    expect(c.error).toEqual({ code: "boom", message: "roto" });
  });
});
