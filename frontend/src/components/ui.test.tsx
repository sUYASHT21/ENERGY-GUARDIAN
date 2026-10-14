import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceBadge, StatTile, StatusPill, commandTone, connectionTone } from "./ui";

describe("ui components", () => {
  it("status pill always carries a text label", () => {
    render(<StatusPill tone="critical" label="Offline" />);
    expect(screen.getByText("Offline")).toBeInTheDocument();
  });

  it("source badges distinguish simulated, emulated and hardware data", () => {
    render(<><SourceBadge source="simulation" /><SourceBadge source="emulator" /><SourceBadge source="hardware" /></>);
    expect(screen.getByText("Simulated")).toBeInTheDocument();
    expect(screen.getByText("Emulated ESP32")).toBeInTheDocument();
    expect(screen.getByText("Hardware")).toBeInTheDocument();
  });

  it("estimate tiles are labelled as estimates", () => {
    render(<StatTile label="Estimated savings" value="1 kWh" tone="estimate" />);
    expect(screen.getByText("Estimate")).toBeInTheDocument();
  });

  it("maps statuses to tones", () => {
    expect(connectionTone("online")).toBe("good");
    expect(connectionTone("offline")).toBe("critical");
    expect(commandTone("acknowledged")).toBe("good");
    expect(commandTone("timeout")).toBe("critical");
    expect(commandTone("blocked")).toBe("serious");
    expect(commandTone("dry_run")).toBe("neutral");
  });
});
