import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useChat } from "../state/chat";
import { useSessions } from "../state/sessions";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const calls: any = { sent: [] };
vi.mock("../transport/chatChannel", () => ({
  startChat: vi.fn().mockResolvedValue({ started: true }),
  sendChat: vi.fn((_ws, _sid, text) => { calls.sent.push(text); return Promise.resolve({}); }),
  interruptChat: vi.fn().mockResolvedValue({}),
  permissionDecision: vi.fn().mockResolvedValue({}),
  subscribeChat: vi.fn(),
}));

import { ChatView } from "./ChatView";

describe("ChatView", () => {
  beforeEach(() => {
    useChat.setState({ convos: {} });
    useSessions.setState({ activeSessionId: "s1", tree: [], repos: [],
      editingId: null, modalParentId: undefined } as any);
  });
  it("renderiza los mensajes de la sesión activa", () => {
    useChat.setState({ convos: { s1: { messages: [{ role: "agent", text: "hola", chips: [] }],
      streaming: false, permission: null, error: null, starting: false } } });
    render(<ChatView />);
    expect(screen.getByText("hola")).toBeInTheDocument();
  });
  it("enviar empuja el mensaje del usuario y llama sendChat", async () => {
    render(<ChatView />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hey" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));
    await waitFor(() => expect(calls.sent).toContain("hey"));
    expect(useChat.getState().convos["s1"].messages.some((m) => m.text === "hey")).toBe(true);
  });
  it("clickear Permitir cierra el prompt de permiso y llama permissionDecision", async () => {
    const { permissionDecision } = await import("../transport/chatChannel");
    useChat.setState({ convos: { s1: { messages: [],
      streaming: false, permission: { id: "p1", tool: "Write", detail: "a.py" },
      error: null, starting: false } } });
    render(<ChatView />);
    expect(screen.getByText(/¿Permitir/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /permitir/i }));
    expect(permissionDecision).toHaveBeenCalledWith(expect.anything(), "s1", "p1", true);
    await waitFor(() => expect(screen.queryByText(/¿Permitir/)).not.toBeInTheDocument());
  });
  it("si startChat rechaza, el error se renderiza en el chat", async () => {
    const { startChat } = await import("../transport/chatChannel");
    (startChat as any).mockRejectedValueOnce(new Error("no logueado"));
    render(<ChatView />);
    await waitFor(() => expect(screen.getByText("no logueado")).toBeInTheDocument());
  });
});
