// ui/src/transport/changesChannel.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchChanges, fetchDiff } from "./changesChannel";

describe("changesChannel", () => {
  it("fetchChanges pide changes.list con sessionId y devuelve status", async () => {
    const status = { name: "repoA", branch: "main", files: [] };
    const ws = { request: vi.fn().mockResolvedValue({ status }) } as any;
    expect(await fetchChanges(ws, { sessionId: "s1" })).toBe(status);
    expect(ws.request).toHaveBeenCalledWith("changes.list", { sessionId: "s1" });
  });

  it("fetchDiff pide changes.diff con path/status y devuelve lines", async () => {
    const lines = [{ type: "add", text: "x" }];
    const ws = { request: vi.fn().mockResolvedValue({ lines }) } as any;
    expect(await fetchDiff(ws, { sessionId: "s1", path: "a.py", status: "M" })).toBe(lines);
    expect(ws.request).toHaveBeenCalledWith("changes.diff", { sessionId: "s1", path: "a.py", status: "M" });
  });

  it("fetchDiff incluye sha cuando se pasa", async () => {
    const ws = { request: vi.fn().mockResolvedValue({ lines: [] }) } as any;
    await fetchDiff(ws, { sessionId: "s1", path: "a.py", status: "M", sha: "abc" });
    expect(ws.request).toHaveBeenCalledWith("changes.diff",
      { sessionId: "s1", path: "a.py", status: "M", sha: "abc" });
  });
});
