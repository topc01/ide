import { describe, it, expect } from "vitest";
import { Search } from "lucide-react";
import { getModules } from "./registry";
import "./search/register";
import "./terminal/register";
import "./changes/register";
import "./graphite/register";
import "./notion/register";
import "./tasks/register";
import { registerModule } from "./registry";
import { useStore } from "../state/store";

const Empty: React.FC = () => null;

describe("module registry", () => {
  it("registra 6 módulos del rail", () => {
    const ids = getModules().map((m) => m.id);
    expect(ids).toEqual(
      expect.arrayContaining(["search", "changes", "graphite", "tasks", "terminal", "notion"]));
    expect(getModules().length).toBeGreaterThanOrEqual(6);
  });

  it("dedup por id: re-registrar un id existente es no-op", () => {
    const before = getModules().length;
    registerModule({ id: "search", title: "Otro", icon: Search, Panel: Empty });
    registerModule({ id: "search", title: "Otro", icon: Search, Panel: Empty });
    expect(getModules().length).toBe(before);
    expect(getModules().filter((m) => m.id === "search")).toHaveLength(1);
  });

  it("el activePanel por defecto es un módulo registrado del rail", () => {
    const ids = getModules().map((m) => m.id);
    expect(ids).toContain(useStore.getState().activePanel);
  });
});
