import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useSettings } from "../../state/settings";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
vi.mock("../../transport/settingsChannel", () => ({
  fetchCustomizations: vi.fn().mockResolvedValue([
    { key: "roles", title: "Roles", description: "", count: 3, rows: [] },
    { key: "tools", title: "Tools", description: "", count: 12, rows: [] },
  ]),
}));
import { CustomizationsFooter } from "./CustomizationsFooter";

beforeEach(() => useSettings.setState({ items: [], open: false, selectedKey: "overview" }));

describe("CustomizationsFooter", () => {
  it("carga los items y abre el modal al clickear uno", async () => {
    render(<CustomizationsFooter />);
    await waitFor(() => screen.getByText("Roles"));
    expect(screen.getByText("Tools")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Roles"));
    expect(useSettings.getState()).toMatchObject({ open: true, selectedKey: "roles" });
  });
});
