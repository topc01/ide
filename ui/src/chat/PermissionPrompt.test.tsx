import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PermissionPrompt } from "./PermissionPrompt";

describe("PermissionPrompt", () => {
  it("muestra la tool y decide allow/deny", () => {
    const onDecide = vi.fn();
    render(<PermissionPrompt tool="Write" detail="a.py" onDecide={onDecide} />);
    expect(screen.getByText(/Write/)).toBeInTheDocument();
    expect(screen.getByText("a.py")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /permitir/i }));
    expect(onDecide).toHaveBeenCalledWith(true);
    fireEvent.click(screen.getByRole("button", { name: /denegar/i }));
    expect(onDecide).toHaveBeenCalledWith(false);
  });
});
