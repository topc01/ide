import { describe, it, expect } from "vitest";
import "../search/register";
import "./register";
import { getModules } from "../registry";
import { ChangesPanel } from "./ChangesPanel";

describe("registro changes", () => {
  it("usa el ChangesPanel real (no el stub)", () => {
    expect(getModules().find((m) => m.id === "changes")?.Panel).toBe(ChangesPanel);
  });
});
