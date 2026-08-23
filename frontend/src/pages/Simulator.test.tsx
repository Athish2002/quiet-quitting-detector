// frontend/src/pages/Simulator.test.tsx

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Simulator } from "./Simulator";

const mockSimulationResult = {
  success: true,
  employee_name: "Custom",
  signals: [
    {
      signal_name: "Response Time Spike",
      signal: "response_time_spike",
      severity: "moderate",
      weeks_detected: [1],
      details: "Average response time increased significantly.",
    },
  ],
  risk_data: {
    score: 42,
    classification: "Watch",
    confidence: "moderate",
    rationale: null,
    model_version: "test-model",
    provenance: null,
    degraded: false,
  },
  briefing: "Check in regarding steady workload pattern.",
};

function renderSimulator() {
  return render(
    <MemoryRouter>
      <Simulator />
    </MemoryRouter>,
  );
}

describe("Simulator", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => mockSimulationResult,
      } as Response)),
    );
  });

  it("renders section header and 5 metric sliders", () => {
    renderSimulator();

    expect(screen.getByText("SIMULATOR")).toBeInTheDocument();
    expect(
      screen.getByText("Try a shape of week and see what it scores."),
    ).toBeInTheDocument();

    expect(screen.getByLabelText(/Tasks completed/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Average response time/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Weekly hours/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/After-hours logins/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Collaboration score/i)).toBeInTheDocument();
  });

  it("updates score and briefing upon computation", async () => {
    renderSimulator();

    await waitFor(() => {
      expect(screen.getByText("42")).toBeInTheDocument();
    });

    expect(screen.getByText("Watch")).toBeInTheDocument();
    expect(
      screen.getByText(/Check in regarding steady workload pattern/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Scratch only/i)).toBeInTheDocument();
  });

  it("reacts to slider change", async () => {
    renderSimulator();

    const slider = screen.getByLabelText(/Tasks completed/i);
    fireEvent.change(slider, { target: { value: "35" } });

    await waitFor(() => {
      expect(screen.getByText("35")).toBeInTheDocument();
    });
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderSimulator();
    await waitFor(() => screen.getByText("42"));
    expect((await axe(container)).violations).toEqual([]);
  });
});
