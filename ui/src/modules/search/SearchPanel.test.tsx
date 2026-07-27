import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SearchPanel } from "./SearchPanel";
import { useStore } from "../../state/store";

vi.mock("../../state/sessions", () => ({ useSessions: (sel: any) => sel({ activeSessionId: "s1" }) }));
const searchContent = vi.fn();
vi.mock("../../transport/searchChannel", () => ({ searchContent: (...a: any[]) => searchContent(...a) }));
vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/filesChannel", () => ({ openFile: vi.fn() }));

beforeEach(() => {
  searchContent.mockReset();
  useStore.setState({ searchQuery: "", searchRegex: true, searchResults: null, searchStatus: "idle", searchError: null,
    searchOptions: { caseSensitive: false, wholeWord: false, include: "", exclude: "", context: 0 } });
});

describe("SearchPanel", () => {
  it("busca con Enter y renderiza resultados agrupados", async () => {
    searchContent.mockResolvedValue({ matches: [{ path: "a.py", lines: [{ line: 2, text: "print(x)", ranges: [[0, 5]] }] }], total: 1, files: 1, truncated: false });
    render(<SearchPanel />);
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: "print" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/buscar/i), { key: "Enter" });
    await waitFor(() => expect(screen.getByText("a.py")).toBeInTheDocument());
    expect(screen.getByText(/1 resultado/i)).toBeInTheDocument();
  });

  it("muestra el error bajo el campo (bad_regex)", async () => {
    searchContent.mockRejectedValue(new Error("regex parse error"));
    render(<SearchPanel />);
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: "(" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/buscar/i), { key: "Enter" });
    await waitFor(() => expect(screen.getByText(/regex parse error/i)).toBeInTheDocument());
  });
});
