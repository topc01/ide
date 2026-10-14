import { describe, it, expect } from "vitest";
import { getGrouper, groupSessions, getGroupers, registerGrouper } from "./groupers";
import type { FolderSession } from "../../transport/folderSessions";

const s = (id: string, status: string | null, process = "stopped"): FolderSession => ({
  id, kind: "ticket", path: "", created: id, permissions: "analyze", title: id, status, meta: {},
  repos: [], error: null, process: process as any, terminalId: null,
});

describe("groupers", () => {
  it("none agrupa todo en una sección", () => {
    const g = groupSessions([s("a", "ready"), s("b", null)], getGrouper("none"));
    expect(g).toHaveLength(1);
    expect(g[0].items.map((x) => x.id)).toEqual(["a", "b"]);
  });

  it("status reparte y omite vacías; Hechos cerrado por defecto", () => {
    const g = groupSessions([
      s("a", "analyzing", "running"), s("b", "blocked"), s("c", "analyzing", "queued"), s("d", "done"),
    ], getGrouper("status"));
    expect(g.map((x) => [x.section.id, x.items.map((i) => i.id)])).toEqual([
      ["active", ["a"]], ["attention", ["b"]], ["queued", ["c"]], ["done", ["d"]]]);
    expect(g[3].section.defaultOpen).toBe(false);
  });

  it("es extensible y getGrouper cae a none", () => {
    registerGrouper({ id: "x", label: "X", sections: [{ id: "all", label: "Todo", defaultOpen: true }],
      sectionOf: () => "all" });
    expect(getGroupers().map((g) => g.id)).toContain("x");
    expect(getGrouper("nope").id).toBe("none");
  });
});
