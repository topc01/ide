import { describe, it, expect, vi } from "vitest";
import { checkHealth, fetchPages, addPage, fetchPage, savePage, setTitle, connect, disconnect } from "./notionChannel";

describe("notionChannel", () => {
  it("checkHealth devuelve connected", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ connected: true }) } as any;
    expect(await checkHealth(ws)).toBe(true);
    expect(ws.request).toHaveBeenCalledWith("notion.health", {});
  });
  it("fetchPages devuelve pages", async () => {
    const pages = [{ id: "a", title: "A" }];
    const ws = { request: vi.fn().mockResolvedValue({ pages }) } as any;
    expect(await fetchPages(ws)).toBe(pages);
  });
  it("addPage manda la url", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ page: { id: "a", title: "A" } }) } as any;
    await addPage(ws, "http://n/x");
    expect(ws.request).toHaveBeenCalledWith("notion.add", { url: "http://n/x" });
  });
  it("fetchPage devuelve el doc", async () => {
    const res = { title: "T", blocks: [], unsupportedIds: [] };
    const ws = { request: vi.fn().mockResolvedValue(res) } as any;
    expect(await fetchPage(ws, "id")).toBe(res);
  });
  it("savePage manda pageId/loaded/edited/unsupportedIds/idMap", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ appended: [], deleted: [], patched: [], failed: [] }) } as any;
    await savePage(ws, "id", [{ id: "b1" }], [{ id: "b1" }], ["u1"], { c: "n" });
    expect(ws.request).toHaveBeenCalledWith("notion.save",
      { pageId: "id", loaded: [{ id: "b1" }], edited: [{ id: "b1" }], unsupportedIds: ["u1"], idMap: { c: "n" } });
  });
  it("setTitle manda pageId y title", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ ok: true }) } as any;
    await setTitle(ws, "id", "Nuevo");
    expect(ws.request).toHaveBeenCalledWith("notion.setTitle", { pageId: "id", title: "Nuevo" });
  });
  it("connect manda el token y devuelve connected", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ connected: true }) } as any;
    expect(await connect(ws, "tok")).toBe(true);
    expect(ws.request).toHaveBeenCalledWith("notion.connect", { token: "tok" });
  });
  it("disconnect llama notion.disconnect", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ connected: false }) } as any;
    await disconnect(ws);
    expect(ws.request).toHaveBeenCalledWith("notion.disconnect", {});
  });
});
