// frontend/src/pages/PersonDetail.test.tsx
//
// Tests for Person Detail (S5):
//   * Renders 66px numeral and risk pill when confidence is high/moderate.
//   * Suppresses the score numeral when confidence is low or none.
//   * Renders weekly trajectories, attributions, patterns, and interventions.
//   * Accessibility (axe) clean with 0 violations.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiKey } from "../api/client";
import { PersonDetail } from "./PersonDetail";
import { generateEmployees, generateBriefing } from "../utils/demoDataGenerator";
const mockEmployees = generateEmployees(5);

const mockBriefing = generateBriefing();

function stubFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: "recorded", week: 6, intervention: "workload_review" }),
        } as Response;
      }
      const routes: Record<string, unknown> = {
        "/employees": mockEmployees,
        "/briefing": mockBriefing,
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

function renderPersonDetail(name = "Ade") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/person/${name}`]}>
        <Routes>
          <Route path="/person/:name" element={<PersonDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PersonDetail (S5)", () => {
  beforeEach(() => {
    setApiKey("test-key");
    stubFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders person name and assessment heading", async () => {
    renderPersonDetail("Ade");
    expect(await screen.findByRole("heading", { name: /Assessment for Ade/i })).toBeInTheDocument();
  });

  it("renders the score numeral when confidence is high", async () => {
    renderPersonDetail("Ade");
    const activeScore = await screen.findByTestId("score-active");
    expect(activeScore).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/Well evidenced/i)).toBeInTheDocument();
  });

  it("SUPPRESSES the score numeral when confidence is low", async () => {
    renderPersonDetail("Priya");
    const suppressed = await screen.findByTestId("score-suppressed");
    expect(suppressed).toBeInTheDocument();
    expect(screen.getByText(/Score withheld — insufficient history/i)).toBeInTheDocument();
    expect(screen.getByText(/Plausible range:/i)).toBeInTheDocument();
    expect(screen.getByText(/4 – 10/i)).toBeInTheDocument();
    expect(screen.queryByTestId("score-active")).toBeNull();
  });

  it("renders trajectory sparklines and attribution metrics", async () => {
    renderPersonDetail("Ade");
    await screen.findByRole("heading", { name: /Weekly Trajectory/i });

    expect(screen.getByText(/completed tasks/i)).toBeInTheDocument();
    expect(screen.getByText(/above baseline/i)).toBeInTheDocument();
    expect(screen.getByText(/Viewing this page writes an immutable entry/i)).toBeInTheDocument();
  });

  it("allows submitting an intervention recommendation", async () => {
    const user = userEvent.setup();
    renderPersonDetail("Priya");
    const button = await screen.findByRole("button", { name: /Schedule Workload 1-on-1/i });
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText(/Recorded intervention/i)).toBeInTheDocument();
    });
  });

  it("has no detectable accessibility violations in high confidence state", async () => {
    const { container } = renderPersonDetail("Ade");
    await screen.findByTestId("score-active");
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it("has no detectable accessibility violations in suppressed score state", async () => {
    const { container } = renderPersonDetail("Priya");
    await screen.findByTestId("score-suppressed");
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });
});
