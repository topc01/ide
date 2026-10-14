import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Queue, QueueSection, QueueSectionTrigger, QueueSectionLabel, QueueSectionContent,
  QueueList, QueueItem, QueueItemContent } from "./queue";

describe("Queue", () => {
  it("sección colapsable con label y contador", () => {
    render(
      <Queue>
        <QueueSection defaultOpen={false}>
          <QueueSectionTrigger><QueueSectionLabel label="Hechos" count={2} /></QueueSectionTrigger>
          <QueueSectionContent>
            <QueueList><QueueItem><QueueItemContent>T-1</QueueItemContent></QueueItem></QueueList>
          </QueueSectionContent>
        </QueueSection>
      </Queue>);
    expect(screen.getByText("Hechos")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("T-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Hechos/ }));
    expect(screen.getByText("T-1")).toBeInTheDocument();
  });
});
