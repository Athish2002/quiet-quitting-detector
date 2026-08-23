// frontend/src/components/TelemetryPulseBar.test.tsx

import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";
import { TelemetryPulseBar } from "./TelemetryPulseBar";

describe("TelemetryPulseBar", () => {
  it("renders the telemetry pulse ribbon and status beacon", () => {
    render(<TelemetryPulseBar />);

    expect(screen.getByText(/Baseline Equilibrium Active/i)).toBeInTheDocument();
    expect(screen.getByText(/Self-Referential Metric Stream/i)).toBeInTheDocument();
    expect(screen.getByText(/Zero-Surveillance Mode/i)).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = render(<TelemetryPulseBar />);
    expect((await axe(container)).violations).toEqual([]);
  });
});
