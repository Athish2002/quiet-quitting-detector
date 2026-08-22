import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiKey } from "../api/client";
import { Cohort, calculateMetricDeviations } from "./Cohort";
import type { EmployeeSummary, RunProgress } from "../api/types";

const mockEmployees: EmployeeSummary[] = [
  {
    name: "Ade",
    score: 2,
    classification: "Healthy",
    rationale: "Steady performance across metrics.",
    latest_week: 6,
    signals: [],
    confidence: "high",
    score_range: [1, 3],
    attributions: [
      {
        metric: "completed_tasks",
        contribution: 0.1,
        effect_size: 0.1,
        direction: "above",
        weeks: [6],
      },
    ],
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
    attributions: [
      {
        metric: "completed_tasks",
        contribution: 0.7,
        effect_size: 0.35,
        direction: "below",
        weeks: [5, 6],
      },
      {
        metric: "response_time",
        contribution: 0.3,
        effect_size: 0.2,
        direction: "above",
        weeks: [6],
      },
    ],
    model_version: "llm-gemini-2.5-flash",
    degraded: true,
    history: [
      { week: 5, score: 6, classification: "At Risk" },
      { week: 6, score: 7, classification: "At Risk" },
    ],
  },
];

const mockProgress: RunProgress = {
  running: false,
  scope: null,
  done: 0,
  total: 0,
  current: "",
  error: null,
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const routes: Record<string, unknown> = {
        "/employees": mockEmployees,
        "/run/progress": mockProgress,
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

function renderCohort() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Cohort />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setApiKey("test-key");
  stubFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Cohort (S4)", () => {
  it("renders the section header with eyebrow and title", async () => {
    renderCohort();
    expect(await screen.findByText("COHORT")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: /Full team telemetry, evaluated against each person's own baseline./i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Listed alphabetically. There is no sort control/i),
    ).toBeInTheDocument();
  });

  it("lists cohort members in alphabetical order", async () => {
    renderCohort();
    await screen.findByText("Ade");

    const cards = screen.getAllByRole("link", { name: /view assessment for/i });
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("Ade")).toBeInTheDocument();
    expect(within(cards[1]!).getByText("Priya")).toBeInTheDocument();
  });

  it("offers no sort controls or ranking affordances", async () => {
    renderCohort();
    await screen.findByText("Ade");

    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByRole("button", { name: /sort/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /rank/i })).toBeNull();
    expect(screen.queryByRole("columnheader")).toBeNull();
  });

  it("renders deviation bars with adverse and inert color logic", () => {
    const attributions = [
      {
        metric: "completed_tasks",
        contribution: 0.7,
        effect_size: 0.25,
        direction: "below",
        weeks: [5, 6],
      },
      {
        metric: "response_time",
        contribution: 0.3,
        effect_size: 0.15,
        direction: "above",
        weeks: [6],
      },
      {
        metric: "after_hours_logins",
        contribution: 0.0,
        effect_size: 0.4,
        direction: "above",
        weeks: [6],
      },
    ];

    const deviations = calculateMetricDeviations(attributions);
    const tasks = deviations.find((d) => d.label === "Tasks completed")!;
    const response = deviations.find((d) => d.label === "Response time")!;
    const afterHours = deviations.find((d) => d.label === "After-hours logins")!;

    expect(tasks.isAdverse).toBe(true);
    expect(tasks.color).toBe("var(--accent)");
    expect(tasks.textColor).toBe("var(--ink)");
    expect(tasks.negW).toBeGreaterThan(0);

    expect(response.isAdverse).toBe(true);
    expect(response.color).toBe("var(--accent)");
    expect(response.textColor).toBe("var(--ink)");
    expect(response.posW).toBeGreaterThan(0);

    // After-hours is always inert regardless of direction
    expect(afterHours.isAdverse).toBe(false);
    expect(afterHours.color).toBe("var(--rule)");
    expect(afterHours.textColor).toBe("var(--muted)");
  });

  it("renders empty state with link to Ingest when no records exist", async () => {
    stubFetch({ "/employees": [] });
    renderCohort();

    expect(await screen.findByText("Nobody on record yet.")).toBeInTheDocument();
    const ingestLink = screen.getByRole("link", { name: /go to ingest/i });
    expect(ingestLink).toHaveAttribute("href", "/ingest");
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderCohort();
    await screen.findByText("Ade");
    expect((await axe(container)).violations).toEqual([]);
  });
});
