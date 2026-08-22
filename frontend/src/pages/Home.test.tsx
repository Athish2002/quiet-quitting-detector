// frontend/src/pages/Home.test.tsx
//
// Tests for the Overview section (S3 of the Modernist redesign).
//
// Asserts the product's standing commitments:
// - All four stat numerals are var(--ink) -- never an alert colour.
// - The band distribution shows COUNTS ONLY, never names, never ranked.
// - No sort control exists anywhere on the page.
// - Populated and empty states both render cleanly and clear axe accessibility.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiKey } from "../api/client";
import type { CalibrationView, EmployeeSummary } from "../api/types";
import { Home } from "./Home";

const populatedEmployees: EmployeeSummary[] = [
  {
    name: "Ade",
    score: 2,
    classification: "Healthy",
    rationale: "Steady performance.",
    latest_week: 6,
    signals: [],
    confidence: "high",
    score_range: [1, 3],
    attributions: [],
    model_version: "llm-gemini-2.5-flash",
    degraded: false,
    history: [
      { week: 5, score: 2, classification: "Healthy" },
      { week: 6, score: 2, classification: "Healthy" },
    ],
  },
  {
    name: "Priya",
    score: 7,
    classification: "At Risk",
    rationale: "Declining task completion.",
    latest_week: 6,
    signals: [
      {
        signal_name: "Declining Task Completion",
        signal: null,
        severity: "high",
        weeks_detected: [5, 6],
        details: null,
      },
    ],
    confidence: "low",
    score_range: [4, 10],
    attributions: [],
    model_version: "llm-gemini-2.5-flash",
    degraded: true,
    history: [
      { week: 5, score: 6, classification: "At Risk" },
      { week: 6, score: 7, classification: "At Risk" },
    ],
  },
];

const populatedCalibration: CalibrationView = {
  active_model_version: "llm-gemini-2.5-flash",
  overall: {
    total: 12,
    accurate: 10,
    not_accurate: 2,
    harmful: 0,
    elevated_precision: 0.83,
    harm_rate: 0.0,
    system_fault_rate: null,
  },
  recent: {
    total: 4,
    accurate: 4,
    not_accurate: 0,
    harmful: 0,
    elevated_precision: 1.0,
    harm_rate: 0.0,
    system_fault_rate: null,
  },
  drifting: false,
  review_required: false,
  message: "12 manager verdict(s) recorded.",
};

const emptyCalibration: CalibrationView = {
  active_model_version: "llm-gemini-2.5-flash",
  overall: {
    total: 0,
    accurate: 0,
    not_accurate: 0,
    harmful: 0,
    elevated_precision: null,
    harm_rate: 0.0,
    system_fault_rate: null,
  },
  recent: {
    total: 0,
    accurate: 0,
    not_accurate: 0,
    harmful: 0,
    elevated_precision: null,
    harm_rate: 0.0,
    system_fault_rate: null,
  },
  drifting: false,
  review_required: false,
  message: "Only 0 manager verdict(s) recorded.",
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const routes: Record<string, unknown> = {
        "/employees": populatedEmployees,
        "/calibration": populatedCalibration,
        ...overrides,
      };
      const key = Object.keys(routes).find((path) => url.includes(path));
      return {
        ok: true,
        status: 200,
        json: async () => (key ? routes[key] : {}),
      } as Response;
    }),
  );
}

function renderOverview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <div className="app-shell">
          <main className="app-main">
            <Home />
          </main>
        </div>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setApiKey("test-key");
  stubFetch();
});

afterEach(() => vi.unstubAllGlobals());

describe("Overview (Home)", () => {
  it("renders the section header with the correct eyebrow and title", async () => {
    renderOverview();

    expect(screen.getByText("OVERVIEW")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /Weekly telemetry, read against a person's own history/i,
      }),
    ).toBeInTheDocument();
  });

  describe("R2 side panels", () => {
    it("renders the band distribution as counts only and never lists employee names", async () => {
      renderOverview();

      const distList = await screen.findByRole("list", {
        name: /people per classification band/i,
      });

      // Healthy: 1, Watch: 0, At Risk: 1, Silent Exit: 0
      expect(within(distList).getByText("Healthy")).toBeInTheDocument();
      expect(within(distList).getByText("Watch")).toBeInTheDocument();
      expect(within(distList).getByText("At Risk")).toBeInTheDocument();
      expect(within(distList).getByText("Silent Exit")).toBeInTheDocument();

      // Counts appear
      const items = within(distList).getAllByRole("listitem");
      expect(items).toHaveLength(4);

      // Crucial: Employee names must NEVER appear in the band distribution or anywhere on Overview
      expect(screen.queryByText("Ade")).toBeNull();
      expect(screen.queryByText("Priya")).toBeNull();
    });

    it("renders the latest evaluation summary without duplicating the active model", async () => {
      renderOverview();

      expect(await screen.findByText("2 people")).toBeInTheDocument();
      expect(screen.getByText("Week 6")).toBeInTheDocument();
      expect(screen.getByText("1 with gaps")).toBeInTheDocument();
      expect(screen.getByText(/Active model: see sidebar/i)).toBeInTheDocument();
    });
  });

  describe("stat strip", () => {
    it("renders all four stat cells with numerals in ink color and no alert colors", async () => {
      renderOverview();

      // Wait for async query data to resolve
      await screen.findByText("12");

      const statStrip = screen.getByRole("region", { name: /summary statistics/i });

      // Verify labels
      expect(within(statStrip).getByText("People on record")).toBeInTheDocument();
      expect(within(statStrip).getByText("Currently raised above Healthy")).toBeInTheDocument();
      expect(within(statStrip).getByText("Manager verdicts recorded")).toBeInTheDocument();
      expect(within(statStrip).getByText("Reported as harmful")).toBeInTheDocument();

      // Verify numerals: 2 on record, 1 raised above Healthy, 12 verdicts, 0 harmful
      const numerals = Array.from(statStrip.querySelectorAll(".stat-cell__numeral"));
      expect(numerals.map((el) => el.textContent)).toEqual(["2", "1", "12", "0"]);

      // HARD CONSTRAINT: No numeral carries a band color class or alert styling
      expect(numerals).toHaveLength(4);
      for (const num of numerals) {
        expect(num.className).not.toMatch(/healthy|watch|at-risk|exit|alert|danger/i);
      }
    });
  });

  describe("constraints and stance", () => {
    it("states what the system does and does not do", async () => {
      renderOverview();

      expect(screen.getByText(/Compare each person to their/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Rank people, or compare one person to another/i),
      ).toBeInTheDocument();
      expect(screen.getByText(/Recommend disciplinary action, ever/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Hold anything about health, sentiment, or performance ratings/i),
      ).toBeInTheDocument();
      expect(screen.getByText(/not a verdict about a person/i)).toBeInTheDocument();
    });

    it("offers no sort control anywhere on the page", async () => {
      renderOverview();
      await waitFor(() => screen.getByText(/People on record/i));

      // There must be no sort buttons or select controls on the overview
      expect(screen.queryByRole("combobox")).toBeNull();
      const sortButtons = screen
        .queryAllByRole("button")
        .filter((btn) => /sort|rank|order/i.test(btn.textContent ?? ""));
      expect(sortButtons).toHaveLength(0);
    });
  });

  describe("link cards", () => {
    it("renders cards linking to Cohort, Diagnostic room, and Access trail", async () => {
      renderOverview();

      const cohortLink = await screen.findByRole("link", { name: /Cohort/i });
      expect(cohortLink).toHaveAttribute("href", "/cohort");

      const diagnosticLink = screen.getByRole("link", { name: /Diagnostic room/i });
      expect(diagnosticLink).toHaveAttribute("href", "/diagnostic");

      const auditLink = screen.getByRole("link", { name: /Access trail/i });
      expect(auditLink).toHaveAttribute("href", "/audit");
    });
  });

  describe("empty state", () => {
    it("renders zero / dash states and notice when no telemetry or verdicts exist", async () => {
      stubFetch({
        "/employees": [],
        "/calibration": emptyCalibration,
      });
      renderOverview();

      await screen.findByText(/No manager verdicts recorded/i);
      expect(
        screen.getByText(/No manager has told this system whether it was right yet/i),
      ).toBeInTheDocument();

      // Numerals are 0
      const numerals = document.querySelectorAll(".stat-cell__numeral");
      expect(numerals).toHaveLength(4);
      for (const num of numerals) {
        expect(num.textContent).toBe("0");
      }

      // Latest telemetry says None
      expect(screen.getByText("None")).toBeInTheDocument();
      expect(screen.getByText("0 people")).toBeInTheDocument();
    });
  });

  describe("accessibility", () => {
    it("has no detectable accessibility violations in populated state", async () => {
      const { container } = renderOverview();
      await waitFor(() => screen.getByText(/People on record/i));
      expect((await axe(container)).violations).toEqual([]);
    });

    it("has no detectable accessibility violations in empty state", async () => {
      stubFetch({
        "/employees": [],
        "/calibration": emptyCalibration,
      });
      const { container } = renderOverview();
      await waitFor(() => screen.getByText(/No manager verdicts recorded/i));
      expect((await axe(container)).violations).toEqual([]);
    });
  });
});
