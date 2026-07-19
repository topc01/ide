import { describe, it, expect, beforeEach, vi } from "vitest";
vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const checkHealth = vi.fn(), fetchPages = vi.fn(), addPage = vi.fn(), removePage = vi.fn(), connectFn = vi.fn(), disconnectFn = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  checkHealth: (...a: any[]) => checkHealth(...a),
  fetchPages: (...a: any[]) => fetchPages(...a),
  addPage: (...a: any[]) => addPage(...a),
  removePage: (...a: any[]) => removePage(...a),
  connect: (...a: any[]) => connectFn(...a),
  disconnect: (...a: any[]) => disconnectFn(...a),
}));
import { useNotion } from "./notion";

beforeEach(() => {
  checkHealth.mockReset(); fetchPages.mockReset(); addPage.mockReset(); removePage.mockReset(); connectFn.mockReset(); disconnectFn.mockReset();
  useNotion.setState({ connected: false, pages: [], loading: false, error: null });
});

describe("state/notion", () => {
  it("load setea connected + pages", async () => {
    checkHealth.mockResolvedValue(true);
    fetchPages.mockResolvedValue([{ id: "a", title: "A" }]);
    await useNotion.getState().load();
    expect(useNotion.getState().connected).toBe(true);
    expect(useNotion.getState().pages).toEqual([{ id: "a", title: "A" }]);
  });
  it("load con error setea error", async () => {
    checkHealth.mockRejectedValue({ message: "boom" });
    await useNotion.getState().load();
    expect(useNotion.getState().error).toBe("boom");
  });
  it("add refresca la lista", async () => {
    checkHealth.mockResolvedValue(true);
    addPage.mockResolvedValue({ id: "b", title: "B" });
    fetchPages.mockResolvedValue([{ id: "b", title: "B" }]);
    await useNotion.getState().add("http://n/b");
    expect(addPage).toHaveBeenCalled();
    expect(useNotion.getState().pages).toEqual([{ id: "b", title: "B" }]);
  });
  it("connect exitoso conecta y carga", async () => {
    connectFn.mockResolvedValue(true);
    checkHealth.mockResolvedValue(true);
    fetchPages.mockResolvedValue([{ id: "a", title: "A" }]);
    await useNotion.getState().connect("tok");
    expect(connectFn).toHaveBeenCalledWith(expect.anything(), "tok");
    expect(useNotion.getState().connected).toBe(true);
    expect(useNotion.getState().pages).toEqual([{ id: "a", title: "A" }]);
  });
  it("connect inválido setea error", async () => {
    connectFn.mockResolvedValue(false);
    await useNotion.getState().connect("bad");
    expect(useNotion.getState().error).toBe("token inválido");
  });
  it("disconnect limpia estado", async () => {
    disconnectFn.mockResolvedValue(undefined);
    useNotion.setState({ connected: true, pages: [{ id: "a", title: "A" }] });
    await useNotion.getState().disconnect();
    expect(useNotion.getState().connected).toBe(false);
    expect(useNotion.getState().pages).toEqual([]);
  });
});
