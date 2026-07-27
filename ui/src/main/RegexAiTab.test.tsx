import { describe, it, expect } from "vitest";
import { extractRegex } from "./RegexAiTab";

describe("extractRegex", () => {
  it("saca el patrón del bloque ```regex```", () => {
    const md = "Probá esto:\n```regex\n\\bprint\\s*\\(\n```\nEso matchea…";
    expect(extractRegex(md)).toBe("\\bprint\\s*\\(");
  });
  it("devuelve null si no hay bloque regex", () => {
    expect(extractRegex("no hay patrón acá")).toBeNull();
  });
  it("toma el último bloque si hay varios", () => {
    const md = "```regex\nfoo\n```\ny mejor:\n```regex\nbar\n```";
    expect(extractRegex(md)).toBe("bar");
  });
});
