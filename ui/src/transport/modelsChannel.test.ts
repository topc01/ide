import { describe, it, expect, vi } from "vitest";
import { fetchModels, downloadModel, deleteModel, subscribeModels } from "./modelsChannel";

describe("modelsChannel", () => {
  it("fetchModels pega a models.list", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ curated: [], installed: [], inUse: null, active: {} }) };
    const cat = await fetchModels(ws as any);
    expect(ws.request).toHaveBeenCalledWith("models.list", {});
    expect(cat.installed).toEqual([]);
  });
  it("downloadModel y deleteModel mandan el repoId", () => {
    const ws = { request: vi.fn().mockResolvedValue({}) } as any;
    downloadModel(ws, "r1"); deleteModel(ws, "r2");
    expect(ws.request).toHaveBeenCalledWith("models.download", { repoId: "r1" });
    expect(ws.request).toHaveBeenCalledWith("models.delete", { repoId: "r2" });
  });
  it("subscribeModels se suscribe y desuscribe de models.event", () => {
    const on = vi.fn(), off = vi.fn();
    const unsub = subscribeModels({ on, off } as any, () => {});
    expect(on).toHaveBeenCalledWith("models.event", expect.any(Function));
    unsub();
    expect(off).toHaveBeenCalledWith("models.event", expect.any(Function));
  });
});
