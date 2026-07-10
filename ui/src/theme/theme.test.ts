// @vitest-environment node
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";

describe("tema 1a (index.css)", () => {
  const css = readFileSync(new URL("../index.css", import.meta.url), "utf8");
  it("define --primary ámbar y --terminal-bg", () => {
    expect(css).toMatch(/--primary:\s*#e0863f/);
    expect(css).toMatch(/--terminal-bg:\s*#0f0e0c/);
    expect(css).toMatch(/--background:\s*#161513/);
  });
});
