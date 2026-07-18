import { describe, it, expect } from "vitest";
import "../stubs";
import "./register";
import { getModules } from "../registry";
import { GraphitePanel } from "./GraphitePanel";

describe("registro graphite", () => {
  it("usa el GraphitePanel real (no el stub)", () => {
    expect(getModules().find((m) => m.id === "graphite")?.Panel).toBe(GraphitePanel);
  });
});
