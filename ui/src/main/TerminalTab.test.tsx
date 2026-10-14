import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

const writes: string[] = [];
let dataCb: ((d: string) => void) | null = null;
vi.mock("@xterm/xterm", () => ({
  Terminal: class {
    write(s: any) { writes.push(typeof s === "string" ? s : "bytes"); }
    onData(cb: (d: string) => void) { dataCb = cb; }
    open() {}
    loadAddon() {}
    dispose() {}
    get cols() { return 80; } get rows() { return 24; }
  },
}));
const fits = { n: 0 };
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() { fits.n++; } } }));
vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const subs: any = {};
vi.mock("../transport/terminalChannel", () => ({
  subscribeTerminal: (_ws: any, _id: string, onData: any) => { subs.onData = onData; return () => {}; },
  writeTerminal: vi.fn(),
  resizeTerminal: vi.fn(),
}));

import { TerminalTab } from "./TerminalTab";
import { writeTerminal, resizeTerminal } from "../transport/terminalChannel";

describe("TerminalTab", () => {
  it("pinta la salida del canal y envía la entrada del usuario", () => {
    render(<TerminalTab id="t1" />);
    subs.onData(new Uint8Array([72, 105]));          // "Hi" del PTY → xterm.write
    expect(writes.length).toBeGreaterThan(0);
    dataCb?.("x");                                    // tecla del usuario → writeTerminal
    expect(writeTerminal).toHaveBeenCalledWith(expect.anything(), "t1", "x");
  });

  it("re-ajusta el tamaño cuando el contenedor cambia (al mostrarse)", () => {
    let cb: (() => void) | null = null;
    const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class {
      constructor(f: () => void) { cb = f; }
      observe() {} disconnect() { disconnect(); }
    });
    const { unmount } = render(<TerminalTab id="t2" />);
    const before = fits.n;
    (resizeTerminal as any).mockClear();
    cb!();
    expect(fits.n).toBe(before + 1);
    expect(resizeTerminal).toHaveBeenCalledWith(expect.anything(), "t2", 80, 24);
    unmount();
    expect(disconnect).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
