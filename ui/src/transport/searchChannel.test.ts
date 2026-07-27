import { describe, it, expect, vi } from "vitest";
import { searchContent } from "./searchChannel";

function fakeWs() {
  const calls: any[] = [];
  return { calls, request: vi.fn((channel, payload) => { calls.push({ channel, payload }); return Promise.resolve({ matches: [], total: 0, files: 0, truncated: false }); }) } as any;
}

describe("searchContent", () => {
  it("manda channel search.content con options normalizadas", async () => {
    const ws = fakeWs();
    await searchContent(ws, "s1", "foo", {
      regex: true, caseSensitive: true, wholeWord: false,
      include: "*.py, *.ts", exclude: "", context: 2,
    });
    expect(ws.calls[0].channel).toBe("search.content");
    expect(ws.calls[0].payload).toEqual({
      sessionId: "s1", query: "foo",
      options: { regex: true, caseSensitive: true, wholeWord: false,
                 include: ["*.py", "*.ts"], exclude: [], context: 2 },
    });
  });
});
