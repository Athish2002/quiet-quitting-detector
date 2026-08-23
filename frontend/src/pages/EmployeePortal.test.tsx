// frontend/src/pages/EmployeePortal.test.tsx

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { EmployeePortal } from "./EmployeePortal";

const mockEmployee = [
  {
    name: "Alex",
    score: 3,
    classification: "Healthy",
    rationale: "Steady pacing.",
    latest_week: 6,
    signals: [],
    confidence: "high",
    history: [
      { week: 5, score: 3, classification: "Healthy" },
      { week: 6, score: 3, classification: "Healthy" },
    ],
  },
];

function renderEmployeePortal() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.includes("/ingest/raw")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ success: true, message: "Raw CSV ingested." }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => mockEmployee,
      } as Response;
    }),
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EmployeePortal />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EmployeePortal", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders section header and privacy assurance", () => {
    renderEmployeePortal();

    expect(screen.getByText("MY WELLBEING")).toBeInTheDocument();
    expect(
      screen.getByText("Your personal workload & reflection space."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Privacy Assurance:/i)).toBeInTheDocument();
  });

  it("submits weekly telemetry and reflection via manual form", async () => {
    renderEmployeePortal();

    const tasksInput = screen.getByLabelText(/Completed Tasks/i);
    fireEvent.change(tasksInput, { target: { value: "28" } });

    const submitBtn = screen.getByRole("button", { name: /Record Weekly Reflection/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Weekly reflection and telemetry successfully recorded/i),
      ).toBeInTheDocument();
    });
  });

  it("renders daily cheer-up card and cycles to next quote on button click", () => {
    renderEmployeePortal();

    expect(screen.getByText(/Self-Compassion/i)).toBeInTheDocument();
    const newCheerupBtn = screen.getByRole("button", { name: /New Cheer-Up/i });
    fireEvent.click(newCheerupBtn);

    expect(screen.getByText(/Rest & Renewal/i)).toBeInTheDocument();
  });

  it("renders personal telemetry log table with recorded history", () => {
    renderEmployeePortal();

    expect(screen.getByText("My Telemetry & Reflection Log")).toBeInTheDocument();
    expect(screen.getByText("Week 5")).toBeInTheDocument();
    expect(screen.getByText("Week 4")).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderEmployeePortal();
    expect((await axe(container)).violations).toEqual([]);
  });
});
