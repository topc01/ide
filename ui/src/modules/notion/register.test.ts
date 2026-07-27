import { describe, it, expect } from "vitest";
import "../search/register";
import "./register";
import { getModules } from "../registry";
import { NotionPanel } from "./NotionPanel";
describe("registro notion", () => {
  it("usa el NotionPanel real", () => {
    expect(getModules().find((m) => m.id === "notion")?.Panel).toBe(NotionPanel);
  });
});
