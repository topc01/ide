import { describe, it, expect, beforeEach } from "vitest";
import { useStore } from "./store";

describe("search state", () => {
  beforeEach(() => useStore.setState({
    searchQuery: "", searchRegex: true, searchResults: null, searchStatus: "idle", searchError: null,
    searchOptions: { caseSensitive: false, wholeWord: false, include: "", exclude: "", context: 0 },
  }));

  it("setSearchQuery y setSearchRegex actualizan", () => {
    useStore.getState().setSearchQuery("foo");
    useStore.getState().setSearchRegex(false);
    expect(useStore.getState().searchQuery).toBe("foo");
    expect(useStore.getState().searchRegex).toBe(false);
  });

  it("setSearchOptions hace merge parcial", () => {
    useStore.getState().setSearchOptions({ wholeWord: true });
    expect(useStore.getState().searchOptions.wholeWord).toBe(true);
    expect(useStore.getState().searchOptions.caseSensitive).toBe(false);
  });

  it("setSearchResults + status", () => {
    useStore.getState().setSearchResults({ matches: [], total: 0, files: 0, truncated: false });
    useStore.getState().setSearchStatus("done");
    expect(useStore.getState().searchStatus).toBe("done");
    expect(useStore.getState().searchResults?.total).toBe(0);
  });
});
