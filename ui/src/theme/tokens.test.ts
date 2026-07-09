import { describe, it, expect } from "vitest";
import { tokens, applyTheme } from "./tokens";

describe("tokens 1a", () => {
  it("accent es amber 1a", () => expect(tokens.accent).toBe("#e0863f"));
  it("applyTheme setea las CSS vars", () => {
    const el = document.createElement("div");
    applyTheme(el);
    expect(el.style.getPropertyValue("--accent")).toBe("#e0863f");
    expect(el.style.getPropertyValue("--app-bg")).toBe("#161513");
  });
  it("applyTheme setea los colores de estado", () => {
    const el = document.createElement("div");
    applyTheme(el);
    expect(el.style.getPropertyValue("--status-running")).toBe("#7fb069");
    expect(el.style.getPropertyValue("--status-idle")).toBe("#7d7568");
    expect(el.style.getPropertyValue("--status-done")).toBe("#6b8fbf");
  });
});
