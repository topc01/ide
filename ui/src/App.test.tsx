// ui/src/App.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("./transport/rest", () => ({
  getRepos: vi.fn().mockResolvedValue([{ id: "repo-a", name: "repo-a", branch: "main" }]),
}));

import App from "./App";
import { useStore } from "./state/store";

describe("App walking skeleton", () => {
  beforeEach(() => useStore.setState({ repos: [] }));
  it("hidrata repos desde el backend y los muestra en el sidebar", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("repo-a")).toBeInTheDocument());
    expect(screen.getByText("main")).toBeInTheDocument();
  });
});
