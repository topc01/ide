import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const fetchChanges = vi.fn();
vi.mock("../transport/changesChannel", () => ({ fetchChanges: (...a: any[]) => fetchChanges(...a) }));

import { useChanges } from "./changes";

beforeEach(() => {
  fetchChanges.mockReset();
  useChanges.setState({ status: null, loading: false, error: null });
});

describe("state/changes", () => {
  it("load exitoso guarda status y limpia error", async () => {
    const status = { branch: "main", files: [] };
    fetchChanges.mockResolvedValue(status);
    await useChanges.getState().load("s1");
    expect(useChanges.getState()).toMatchObject({ status, error: null, loading: false });
  });

  it("load con error limpia status y setea error", async () => {
    useChanges.setState({ status: { branch: "old", files: [] } as any });
    fetchChanges.mockRejectedValue({ message: "no es repo git" });
    await useChanges.getState().load("s1");
    expect(useChanges.getState().status).toBeNull();
    expect(useChanges.getState().error).toBe("no es repo git");
  });
});
