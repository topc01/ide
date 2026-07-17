import { describe, it, expect, vi } from "vitest";
import { fetchCustomizations } from "./settingsChannel";
describe("settingsChannel", () => {
  it("fetchCustomizations pide customizations.list y devuelve items", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ items: [{ key: "roles" }] }) } as any;
    expect(await fetchCustomizations(ws)).toEqual([{ key: "roles" }]);
    expect(ws.request).toHaveBeenCalledWith("customizations.list", {});
  });
});
