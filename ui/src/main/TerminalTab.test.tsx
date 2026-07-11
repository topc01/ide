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
vi.mock("@xterm/addon-fit", () => ({ FitAddon: class { fit() {} } }));
vi.mock("../transport/wsClient", () => ({ getWs: () => ({}) }));
const subs: any = {};
vi.mock("../transport/terminalChannel", () => ({
  subscribeTerminal: (_ws: any, _id: string, onData: any) => { subs.onData = onData; },
  writeTerminal: vi.fn(),
  resizeTerminal: vi.fn(),
}));

import { TerminalTab } from "./TerminalTab";
import { writeTerminal } from "../transport/terminalChannel";

describe("TerminalTab", () => {
  it("pinta la salida del canal y envía la entrada del usuario", () => {
    render(<TerminalTab id="t1" />);
    subs.onData(new Uint8Array([72, 105]));          // "Hi" del PTY → xterm.write
    expect(writes.length).toBeGreaterThan(0);
    dataCb?.("x");                                    // tecla del usuario → writeTerminal
    expect(writeTerminal).toHaveBeenCalledWith(expect.anything(), "t1", "x");
  });
});
