import { describe, it, expect, beforeEach, vi } from "vitest";
vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const checkHealth = vi.fn(), fetchPages = vi.fn(), addPage = vi.fn(), removePage = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  checkHealth: (...a: any[]) => checkHealth(...a),
  fetchPages: (...a: any[]) => fetchPages(...a),
  addPage: (...a: any[]) => addPage(...a),
  removePage: (...a: any[]) => removePage(...a),
}));
import { useNotion } from "./notion";

beforeEach(() => {
  checkHealth.mockReset(); fetchPages.mockReset(); addPage.mockReset(); removePage.mockReset();
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
});
