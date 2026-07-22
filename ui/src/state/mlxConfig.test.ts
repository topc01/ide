import { describe, it, expect, beforeEach } from "vitest";
import { useMlxConfig } from "./mlxConfig";

beforeEach(() => useMlxConfig.setState({ enabled: false, model: "", routerPrompt: "", defaultPrompt: "", loaded: false, error: null }));

describe("useMlxConfig", () => {
  it("setConfig puebla y marca loaded", () => {
    useMlxConfig.getState().setConfig({ enabled: true, model: "m", routerPrompt: "p", defaultPrompt: "d" });
    const s = useMlxConfig.getState();
    expect(s.enabled).toBe(true); expect(s.model).toBe("m"); expect(s.loaded).toBe(true);
  });
  it("update muta un campo", () => {
    useMlxConfig.getState().update({ model: "x" });
    expect(useMlxConfig.getState().model).toBe("x");
  });
  it("setError guarda el error", () => {
    useMlxConfig.getState().setError("boom");
    expect(useMlxConfig.getState().error).toBe("boom");
  });
});
