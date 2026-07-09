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
});
