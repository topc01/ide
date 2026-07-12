import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";

describe("MessageBubble", () => {
  it("muestra texto de agente con chip de tool y edit +/-", () => {
    render(<MessageBubble msg={{ role: "agent", text: "listo", tokens: 42, chips: [
      { kind: "tool", name: "Bash", detail: "ls -la" },
      { kind: "edit", path: "a.py", added: 3, removed: 1 },
    ] }} />);
    expect(screen.getByText("listo")).toBeInTheDocument();
    expect(screen.getByText("Bash")).toBeInTheDocument();
    expect(screen.getByText("ls -la")).toBeInTheDocument();
    expect(screen.getByText("a.py")).toBeInTheDocument();
    expect(screen.getByText("+3")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
    expect(screen.getByText(/42 tokens/)).toBeInTheDocument();
  });
  it("burbuja de usuario usa la clase de accent", () => {
    render(<MessageBubble msg={{ role: "user", text: "hola", chips: [] }} />);
    const bubble = screen.getByText("hola").closest("[data-bubble]") as HTMLElement;
    expect(bubble.className).toContain("bg-primary");
  });
});
