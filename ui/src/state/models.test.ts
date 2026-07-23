import { describe, it, expect, beforeEach } from "vitest";
import { useModels } from "./models";

beforeEach(() => useModels.setState({ curated: [], installed: [], inUse: null, downloads: {}, fit: {} }));

describe("useModels", () => {
  it("progress y done actualizan downloads", () => {
    const { applyEvent } = useModels.getState();
    applyEvent({ kind: "progress", repoId: "r1", downloaded: 50, total: 100 });
    expect(useModels.getState().downloads["r1"]).toEqual({ downloaded: 50, total: 100 });
    applyEvent({ kind: "done", repoId: "r1" });
    expect(useModels.getState().downloads["r1"].done).toBe(true);
  });
  it("error guarda el mensaje", () => {
    useModels.getState().applyEvent({ kind: "error", repoId: "r1", message: "boom" });
    expect(useModels.getState().downloads["r1"].error).toBe("boom");
  });
  it("setCatalog puebla curated/installed/inUse", () => {
    useModels.getState().setCatalog({
      curated: [{ repoId: "a", label: "A", params: "1B", quant: "4bit", sizeGb: 0.7 }],
      installed: [{ repoId: "a", sizeOnDisk: 100 }], inUse: "a", active: {},
    });
    const s = useModels.getState();
    expect(s.curated).toHaveLength(1); expect(s.inUse).toBe("a");
  });
  it("setFit puebla el fit", () => {
    useModels.getState().setFit({ "a": { level: "ok", fitLabel: "Perfect", memoryRequiredGb: 6.7,
      memoryAvailableGb: 24, estimatedTps: 9.5, diskSizeGb: 5.8, bestQuant: "mlx-8bit",
      contextLength: 32768, score: 87, scoreComponents: { fit: 100, speed: 20, quality: 99, context: 100 } } });
    expect(useModels.getState().fit["a"]?.level).toBe("ok");
  });
});
