import { describe, it, expect, beforeEach } from "vitest";
import { useSettings } from "./settings";
beforeEach(() => useSettings.setState({ items: [], open: false, selectedKey: "overview" }));
describe("useSettings", () => {
  it("openSettings abre en el item elegido; closeSettings cierra", () => {
    useSettings.getState().openSettings("roles");
    expect(useSettings.getState()).toMatchObject({ open: true, selectedKey: "roles" });
    useSettings.getState().closeSettings();
    expect(useSettings.getState().open).toBe(false);
  });
  it("setData guarda los items", () => {
    useSettings.getState().setData([{ key: "roles", title: "Roles", description: "", count: 1, rows: [] }] as any);
    expect(useSettings.getState().items).toHaveLength(1);
  });
});
