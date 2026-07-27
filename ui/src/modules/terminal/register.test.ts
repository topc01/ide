import { describe, it, expect } from "vitest";
import "../search/register";
import "./register";
import { getModules } from "../registry";
import { TerminalPanel } from "./TerminalPanel";

describe("registro terminal", () => {
  it("usa el TerminalPanel real", () => {
    expect(getModules().find((m) => m.id === "terminal")?.Panel).toBe(TerminalPanel);
  });
});
