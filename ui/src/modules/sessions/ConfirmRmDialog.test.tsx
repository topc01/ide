import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("../../transport/wsClient", () => ({ getWs: () => ({}) }));
const rmSession = vi.fn().mockRejectedValue({ code: "uncommitted_changes", message: "cambios sin commitear" });
vi.mock("../../transport/folderSessions", async (orig) => ({
  ...(await orig<any>()), rmSession: (...a: any[]) => rmSession(...a),
}));

import { ConfirmRmDialog } from "./ConfirmRmDialog";

describe("ConfirmRmDialog", () => {
  it("al reabrir no arrastra el error ni el --force anterior", async () => {
    const { rerender } = render(<ConfirmRmDialog id="a" open onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Borrar" }));
    expect(await screen.findByText("cambios sin commitear")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /--force/ })).toBeInTheDocument();
    rerender(<ConfirmRmDialog id="a" open={false} onClose={() => {}} />);
    rerender(<ConfirmRmDialog id="a" open onClose={() => {}} />);
    expect(screen.queryByText("cambios sin commitear")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Borrar" })).toBeInTheDocument();
  });
});
