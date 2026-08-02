// The tests here are mostly about what the interface must NOT let a reader
// take away. The backend already refuses to hide uncertainty or to present
// association as causation; a dashboard is exactly where those guarantees get
// quietly undone by putting the number in large type and the caveat in grey.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiKey } from "../api/client";
import type { CalibrationView, InterventionOutcomes } from "../api/types";
import { ScoreDisplay } from "../components/ConfidenceBadge";
import { DiagnosticRoom } from "./DiagnosticRoom";

// Typed against the generated response types, so a fixture cannot describe a
// response the API does not send.
const calibration: CalibrationView = {
  active_model_version: "llm-gemini-2.5-flash",
  overall: {
    total: 3,
    accurate: 2,
    not_accurate: 1,
    harmful: 0,
    elevated_precision: null,
    harm_rate: 0,
    system_fault_rate: null,
  },
  recent: {
    total: 3,
    accurate: 2,
    not_accurate: 1,
    harmful: 0,
    elevated_precision: null,
    harm_rate: 0,
    system_fault_rate: null,
  },
  drifting: false,
  review_required: false,
  message:
    "Only 3 manager verdict(s) recorded. Not enough to say whether this system is calibrated -- treat every score as unvalidated.",
};

const outcomes: InterventionOutcomes = {
  association_only: true as const,
  caveat:
    "These are observational outcomes with no control group. People are flagged at their most extreme and tend to move back toward their own normal regardless of what anyone does.",
  by_type: [
    {
      intervention: "workload_adjustment",
      sample_size: 6,
      median_excess_recovery: 0.8,
      improved: 4,
      declined: 1,
      no_change: 1,
      reportable: true,
      note: "Association only.",
    },
    {
      intervention: "check_in",
      sample_size: 2,
      median_excess_recovery: null,
      improved: 0,
      declined: 0,
      no_change: 0,
      reportable: false,
      note: "Only 2 measured outcome(s). Too few to say anything about this practice.",
    },
  ],
  measured_outcomes: 8,
  examples: [],
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DiagnosticRoom />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setApiKey("test-key");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.includes("/calibration") ? calibration : outcomes;
      return {
        ok: true,
        status: 200,
        json: async () => body,
      } as Response;
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Diagnostic room", () => {
  it("says plainly when there is not enough feedback to judge the system", async () => {
    renderPage();
    expect(
      await screen.findByText(/treat every score as unvalidated/i),
    ).toBeInTheDocument();
  });

  it("shows the causation caveat before any intervention numbers", async () => {
    renderPage();
    const caveat = await screen.findByText(/no control group/i);
    const table = await screen.findByRole("table");

    // Order matters: a reader who stops after the first thing they see must
    // still have been told these are not causal.
    expect(
      caveat.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("never labels an intervention outcome as a cause", async () => {
    renderPage();
    await screen.findByRole("table");
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/association only/i);
    expect(text).not.toMatch(/\bcaused by\b|\bproves\b|\bbecause of the intervention\b/i);
  });

  it("reports an unevaluated practice rather than hiding it", async () => {
    renderPage();
    expect(
      await screen.findByText(/Too few to say anything about this practice/i),
    ).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderPage();
    await screen.findByRole("table");
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it("labels every form control", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/week/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("group", { name: /your verdict/i })).toBeInTheDocument();
  });
});

describe("Score display", () => {
  it("refuses to show a single number when confidence is low", () => {
    render(<ScoreDisplay score={7} range={[4, 10]} confidence="low" />);

    expect(screen.getByText(/not confident enough/i)).toBeInTheDocument();
    expect(screen.queryByText("7")).not.toBeInTheDocument();
    expect(screen.getByText(/4–10/)).toBeInTheDocument();
  });

  it("does not call the range a confidence interval", () => {
    render(<ScoreDisplay score={7} range={[4, 10]} confidence="low" />);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/not a statistical confidence interval/i);
  });

  it("shows the number when the evidence supports it", () => {
    render(<ScoreDisplay score={7} range={[6, 8]} confidence="high" />);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText(/well evidenced/i)).toBeInTheDocument();
  });
});
