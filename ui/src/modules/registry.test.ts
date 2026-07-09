import { describe, it, expect } from "vitest";
import { getModules } from "./stubs";

describe("module registry", () => {
  it("registra 6 módulos del rail", () => {
    const ids = getModules().map((m) => m.id);
    expect(ids).toEqual(
      expect.arrayContaining(["search", "changes", "graphite", "tasks", "terminal", "notion"]));
    expect(getModules().length).toBeGreaterThanOrEqual(6);
  });
});
