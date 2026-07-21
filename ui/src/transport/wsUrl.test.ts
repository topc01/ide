import { describe, it, expect } from "vitest";
import { wsUrl } from "./wsUrl";

describe("wsUrl", () => {
  it("prod: mismo origen con el puerto real", () => {
    expect(wsUrl({ DEV: false }, { protocol: "http:", host: "127.0.0.1:8788" }))
      .toBe("ws://127.0.0.1:8788/ws");
  });
  it("prod https → wss", () => {
    expect(wsUrl({ DEV: false }, { protocol: "https:", host: "ide.example.com" }))
      .toBe("wss://ide.example.com/ws");
  });
  it("dev: backend en :8787", () => {
    expect(wsUrl({ DEV: true }, { protocol: "http:", host: "localhost:5173" }))
      .toBe("ws://localhost:8787/ws");
  });
});
