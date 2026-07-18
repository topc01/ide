import { describe, it, expect, vi } from "vitest";
import { fetchStack, fetchBranch, restackBranch } from "./graphiteChannel";

describe("graphiteChannel", () => {
  it("fetchStack pide graphite.stack y devuelve {stack,current}", async () => {
    const res = { stack: [{ name: "main" }], current: "main" };
    const ws = { request: vi.fn().mockResolvedValue(res) } as any;
    expect(await fetchStack(ws, { sessionId: "s1" })).toBe(res);
    expect(ws.request).toHaveBeenCalledWith("graphite.stack", { sessionId: "s1" });
  });

  it("fetchBranch pide graphite.branch y devuelve commits", async () => {
    const commits = [{ hash: "a", message: "m", files: [] }];
    const ws = { request: vi.fn().mockResolvedValue({ commits }) } as any;
    expect(await fetchBranch(ws, { sessionId: "s1", branch: "feat-a" })).toBe(commits);
    expect(ws.request).toHaveBeenCalledWith("graphite.branch", { sessionId: "s1", branch: "feat-a" });
  });

  it("restackBranch pide graphite.restack y devuelve {stack,current}", async () => {
    const res = { stack: [], current: "main" };
    const ws = { request: vi.fn().mockResolvedValue(res) } as any;
    expect(await restackBranch(ws, { sessionId: "s1", branch: "feat-a" })).toBe(res);
    expect(ws.request).toHaveBeenCalledWith("graphite.restack", { sessionId: "s1", branch: "feat-a" });
  });
});
