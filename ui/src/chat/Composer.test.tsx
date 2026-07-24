import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("envía el texto (Auto → sin route) y limpia el input", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} onStop={() => {}} streaming={false} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hola" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));
    expect(onSend).toHaveBeenCalledWith("hola", undefined);          // Auto → sin override
    expect(input.value).toBe("");
  });
  it("con el selector en Local envía route=local", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} onStop={() => {}} streaming={false} />);
    fireEvent.change(screen.getByLabelText(/ruteo/i), { target: { value: "local" } });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hola" } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));
    expect(onSend).toHaveBeenCalledWith("hola", "local");
  });
  it("no envía vacío", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} onStop={() => {}} streaming={false} />);
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));
    expect(onSend).not.toHaveBeenCalled();
  });
  it("muestra stop cuando streaming", () => {
    const onStop = vi.fn();
    render(<Composer onSend={() => {}} onStop={onStop} streaming={true} />);
    fireEvent.click(screen.getByRole("button", { name: /detener/i }));
    expect(onStop).toHaveBeenCalled();
  });
});
