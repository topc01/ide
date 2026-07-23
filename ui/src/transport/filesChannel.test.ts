import { describe, it, expect, vi } from "vitest";
import { listFiles, openFile } from "./filesChannel";

describe("filesChannel", () => {
  it("listFiles pega a files.list con sessionId y path", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ entries: [] }) } as any;
    await listFiles(ws, "s1", "src");
    expect(ws.request).toHaveBeenCalledWith("files.list", { sessionId: "s1", path: "src" });
  });
  it("openFile pega a files.open", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ id: "t1", cwd: "/x" }) } as any;
    const r = await openFile(ws, "s1", "a.txt");
    expect(ws.request).toHaveBeenCalledWith("files.open", { sessionId: "s1", path: "a.txt" });
    expect(r.id).toBe("t1");
  });
});
