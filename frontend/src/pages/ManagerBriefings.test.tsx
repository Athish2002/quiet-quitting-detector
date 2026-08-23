// frontend/src/pages/ManagerBriefings.test.tsx

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { ManagerBriefings } from "./ManagerBriefings";

const mockEmployees = [
  {
    name: "Ade",
    score: 2,
    classification: "Healthy",
    rationale: "Steady performance across all weeks.",
    latest_week: 6,
    signals: [],
    confidence: "high",
  },
  {
    name: "Priya",
    score: 7,
    classification: "At Risk",
    rationale: "Increased response times and overwork detected.",
    latest_week: 6,
    signals: [],
    confidence: "moderate",
  },
];

function renderManagerBriefings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => mockEmployees,
    } as Response)),
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ManagerBriefings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ManagerBriefings", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders section header and supportive manager stance", async () => {
    renderManagerBriefings();

    expect(screen.getByText("SUPPORTIVE BRIEFINGS")).toBeInTheDocument();
    expect(
      screen.getByText("Mental wellbeing & 1-on-1 check-in guides."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Manager Stance:/i)).toBeInTheDocument();
  });

  it("renders team roster and selected 1-on-1 check-in guide", async () => {
    renderManagerBriefings();

    await waitFor(() => {
      expect(screen.getByText("1-on-1 Check-in Guide: Ade")).toBeInTheDocument();
    });

    expect(screen.getByText("Suggested Conversation Starters")).toBeInTheDocument();
    expect(screen.getByText("Constructive Wellbeing Interventions")).toBeInTheDocument();

    // Switch to Priya
    const priyaBtn = screen.getByRole("button", { name: /Priya/i });
    fireEvent.click(priyaBtn);

    expect(screen.getByText("1-on-1 Check-in Guide: Priya")).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderManagerBriefings();
    await waitFor(() => screen.getByText("1-on-1 Check-in Guide: Ade"));
    expect((await axe(container)).violations).toEqual([]);
  });
});
