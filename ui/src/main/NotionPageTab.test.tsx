import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchPage = vi.fn(), savePage = vi.fn(), setTitle = vi.fn();
vi.mock("../transport/notionChannel", () => ({
  fetchPage: (...a: any[]) => fetchPage(...a),
  savePage: (...a: any[]) => savePage(...a),
  setTitle: (...a: any[]) => setTitle(...a),
}));
// El mock del editor dispara onChange con un doc que agrega un bloque nuevo "c2".
vi.mock("./NotionEditor", () => ({
  NotionEditor: ({ onChange }: any) => (
    <button onClick={() => onChange([
      { id: "b1", type: "paragraph", content: [] },
      { id: "c2", type: "paragraph", content: [{ type: "text", text: "z", styles: {} }] },
    ])}>edit</button>
  ),
}));
import { NotionPageTab } from "./NotionPageTab";

beforeEach(() => { fetchPage.mockReset(); savePage.mockReset(); setTitle.mockReset(); vi.useFakeTimers(); });

describe("NotionPageTab Fase 2", () => {
  it("guarda con idMap y fusiona appended sin remontar (happy path)", async () => {
    fetchPage.mockResolvedValue({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: ["u1"] });
    savePage.mockResolvedValue({ appended: [{ clientId: "c2", notionId: "n2" }], deleted: [], patched: [], failed: [] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));

    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    // primer save: idMap vacío
    expect(savePage).toHaveBeenLastCalledWith(expect.anything(), "pageX",
      expect.any(Array), expect.any(Array), ["u1"], {});

    // segunda edición del mismo doc: ahora idMap debe mapear c2->n2
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    expect(savePage).toHaveBeenLastCalledWith(expect.anything(), "pageX",
      expect.any(Array), expect.any(Array), ["u1"], { c2: "n2" });
    // happy path: no hubo re-fetch de reconciliación (solo el fetch inicial)
    expect(fetchPage).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("re-fetch de reconciliación cuando una op falla", async () => {
    fetchPage
      .mockResolvedValueOnce({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: [] })
      .mockResolvedValueOnce({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: [] });
    savePage.mockResolvedValue({ appended: [], deleted: [], patched: [], failed: [{ op: "append", id: "c2", message: "boom" }] });
    render(<NotionPageTab id="notion:pageX" />);
    await vi.waitFor(() => screen.getByText("edit"));
    screen.getByText("edit").click();
    await vi.advanceTimersByTimeAsync(900);
    await vi.waitFor(() => expect(fetchPage).toHaveBeenCalledTimes(2));
    vi.useRealTimers();
  });

  it("editar el título llama setTitle en blur", async () => {
    fetchPage.mockResolvedValue({ title: "T", blocks: [{ id: "b1", type: "paragraph", content: [] }], unsupportedIds: [] });
    setTitle.mockResolvedValue(undefined);
    render(<NotionPageTab id="notion:pageX" />);
    const input = await vi.waitFor(() => screen.getByDisplayValue("T"));
    fireEvent.change(input, { target: { value: "Nuevo" } });
    fireEvent.blur(input);
    expect(setTitle).toHaveBeenCalledWith(expect.anything(), "pageX", "Nuevo");
    vi.useRealTimers();
  });
});
