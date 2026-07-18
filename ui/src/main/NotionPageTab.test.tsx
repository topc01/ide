import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchPage = vi.fn(), savePage = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  fetchPage: (...a: any[]) => fetchPage(...a),
  savePage: (...a: any[]) => savePage(...a),
}));
// Mock del editor: expone un botón que dispara onChange con un doc editado.
vi.mock("./NotionEditor", () => ({
  NotionEditor: ({ onChange }: any) => (
    <button onClick={() => onChange([{ id: "b1", type: "paragraph", content: [{ type: "text", text: "z", styles: {} }] }])}>edit</button>
  ),
}));
import { NotionPageTab } from "./NotionPageTab";

beforeEach(() => { fetchPage.mockReset(); savePage.mockReset(); vi.useFakeTimers(); });

describe("NotionPageTab", () => {
  it("carga la página y guarda (debounce) al editar", async () => {
    fetchPage.mockResolvedValue({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: ["u1"] });
    savePage.mockResolvedValue({ applied: 1, structural: false, failed: [] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    expect(savePage).toHaveBeenCalledWith(expect.anything(), "pageX",
      [{ id: "b1", type: "paragraph", content: [] }], expect.any(Array), ["u1"]);
    vi.useRealTimers();
  });

  it("re-sincroniza (re-fetch) el editor tras un guardado estructural", async () => {
    fetchPage
      .mockResolvedValueOnce({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: ["u1"] })
      .mockResolvedValueOnce({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }, { id: "b2", type: "paragraph", content: [] }], unsupportedIds: [] });
    savePage.mockResolvedValue({ applied: 1, structural: true, failed: [] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    await vi.waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(2));
    vi.useRealTimers();
  });
});
