// Tests for the three pages migrated after the Diagnostic Room.
//
// Same emphasis as DiagnosticRoom.test.tsx: most of these check what the
// interface must NOT let a reader take away. The backend already refuses to
// rank people or hide uncertainty; a dashboard is where those guarantees get
// quietly undone by a sort control or a bold number.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiKey } from "../api/client";
import type {
  CalibrationView,
  EmployeeSummary,
  HistoryEvent,
  ProviderStatus,
  RunProgress,
} from "../api/types";
import { Console } from "./Console";
import { History } from "./History";
import { Home } from "./Home";

// The fixtures are TYPED against the generated response types on purpose. An
// untyped mock is free to describe a response the API does not send, and this
// file used to do exactly that -- `event_type` below was a field no handler has
// ever returned, so the test agreed with the page and both were wrong.
const employees: EmployeeSummary[] = [
  {
    name: "Ade",
    score: 2,
    classification: "Healthy",
    rationale: "Steady.",
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
    // Thin evidence: the score must NOT be rendered.
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

const calibration: CalibrationView = {
  active_model_version: "llm-gemini-2.5-flash",
  overall: {
    total: 0,
    accurate: 0,
    not_accurate: 0,
    harmful: 0,
    elevated_precision: null,
    harm_rate: 0,
    system_fault_rate: null,
  },
  recent: {
    total: 0,
    accurate: 0,
    not_accurate: 0,
    harmful: 0,
    elevated_precision: null,
    harm_rate: 0,
    system_fault_rate: null,
  },
  drifting: false,
  review_required: false,
  message: "Only 0 manager verdict(s) recorded.",
};

const historyEvents: HistoryEvent[] = [
  {
    timestamp: "2026-07-31T10:00:00Z",
    action: "ingest",
    source: "csv_paste",
    detail: "6 row(s) across week 6.",
    success: true,
  },
];

const progress: RunProgress = {
  running: false,
  scope: null,
  done: 0,
  total: 0,
  current: "",
  error: null,
};

const providerStatus: ProviderStatus = {
  fallback_sequence: [],
  last_successful_model: null,
  exhausted_models: [],
  local_only_mode: false,
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const routes: Record<string, unknown> = {
        "/employees": employees,
        "/calibration": calibration,
        "/history": historyEvents,
        "/run/progress": progress,
        "/models/status": providerStatus,
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

/** Match text that JSX split across <strong>/<em> and interpolations.
 *  Testing Library's default matcher only sees text inside a single element,
 *  and breaking a sentence for emphasis is exactly what these pages do. */
function hasText(pattern: RegExp) {
  return (_content: string, element: Element | null) => {
    if (!element) return false;
    const own = element.textContent ?? "";
    const childMatches = Array.from(element.children).some((child) =>
      pattern.test(child.textContent ?? ""),
    );
    return pattern.test(own) && !childMatches;
  };
}

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setApiKey("test-key");
  stubFetch();
});

afterEach(() => vi.unstubAllGlobals());

// ---------------------------------------------------------------------------
// Console
// ---------------------------------------------------------------------------
describe("Console", () => {
  it("lists the cohort alphabetically and says it is not a ranking", async () => {
    renderPage(<Console />);
    await screen.findByRole("table");

    const rows = screen.getAllByRole("rowheader").map((cell) => cell.textContent);
    expect(rows).toEqual(["Ade", "Priya"]);
    expect(screen.getByText(/not a ranking/i)).toBeInTheDocument();
  });

  it("offers no way to sort the cohort by risk", async () => {
    renderPage(<Console />);
    await screen.findByRole("table");

    // A sort control on this table is the feature that turns a wellbeing tool
    // into a leaderboard. There must not be one.
    const headers = screen.getAllByRole("columnheader");
    for (const header of headers) {
      expect(within(header).queryByRole("button")).toBeNull();
      expect(header).not.toHaveAttribute("aria-sort");
    }
  });

  it("withholds the score for someone with thin evidence", async () => {
    renderPage(<Console />);
    await screen.findByRole("table");

    const priyaRow = screen.getByRole("rowheader", { name: "Priya" }).closest("tr")!;
    expect(within(priyaRow).getByText(/At Risk/)).toBeInTheDocument();
    expect(within(priyaRow).getByText(/not enough evidence/i)).toBeInTheDocument();
    expect(within(priyaRow).queryByText("7/10")).toBeNull();

    // And it shows the score where the evidence supports it.
    const adeRow = screen.getByRole("rowheader", { name: "Ade" }).closest("tr")!;
    expect(within(adeRow).getByText(/2\/10/)).toBeInTheDocument();
  });

  it("asks before destroying the cohort", async () => {
    const user = userEvent.setup();
    renderPage(<Console />);
    await screen.findByRole("table");

    await user.click(screen.getByRole("button", { name: /regenerate demo data/i }));
    expect(screen.getByText(/deletes every stored evaluation/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /yes, regenerate/i }),
    ).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderPage(<Console />);
    await screen.findByRole("table");
    expect((await axe(container)).violations).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------
describe("History", () => {
  it("separates the clearable event log from the access audit trail", async () => {
    renderPage(<History />);
    await screen.findByRole("table");

    expect(screen.getByText(hasText(/is not the access audit trail/i))).toBeInTheDocument();
    expect(screen.getByText(hasText(/cannot be cleared/i))).toBeInTheDocument();

    // The only clear button on the page is for the operational log.
    const clearButtons = screen
      .getAllByRole("button")
      .filter((b) => /clear/i.test(b.textContent ?? ""));
    expect(clearButtons).toHaveLength(1);
  });

  it("shows what each logged event actually was", async () => {
    // The assertion whose absence let a real bug live: the page read
    // `event_type`, the API sends `action`, and every row in this column
    // rendered an em-dash. Nothing looked broken -- an em-dash is what an
    // empty cell is supposed to look like.
    renderPage(<History />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText(/ingest \/ csv_paste/)).toBeInTheDocument();
  });

  it("says each person is compared only against themselves", async () => {
    renderPage(<History />);
    await screen.findByText(/week by week/i);
    expect(
      screen.getByText(hasText(/compared against their own earlier weeks/i)),
    ).toBeInTheDocument();
    expect(
      screen.getByText(hasText(/never compared to each other/i)),
    ).toBeInTheDocument();
  });

  it("does not depend on colour to convey a classification", async () => {
    renderPage(<History />);
    // Wait for the DATA, not just the heading -- the sparklines do not exist
    // until the query resolves.
    await screen.findByText(/W6: Healthy/);

    // The bars are decorative; the classification is in text beside them.
    expect(screen.getAllByText(/W6: (Healthy|At Risk)/).length).toBeGreaterThan(0);
    for (const bar of document.querySelectorAll(".bar")) {
      expect(bar).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("asks before clearing the event log", async () => {
    const user = userEvent.setup();
    renderPage(<History />);
    await screen.findByRole("button", { name: /clear event log/i });

    await user.click(screen.getByRole("button", { name: /clear event log/i }));
    expect(screen.getByRole("button", { name: /yes, clear it/i })).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderPage(<History />);
    await screen.findByRole("table");
    expect((await axe(container)).violations).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------------
describe("Home", () => {
  it("states what the system will not do before showing any controls", async () => {
    renderPage(<Home />);

    expect(screen.getByText(/Rank people, or compare one person to another/i)).toBeInTheDocument();
    expect(screen.getByText(/Recommend disciplinary action, ever/i)).toBeInTheDocument();
    expect(screen.getByText(/not a verdict about a person/i)).toBeInTheDocument();
  });

  it("reports a count of flagged people, never a list of names", async () => {
    renderPage(<Home />);
    await waitFor(() => {
      expect(screen.getByText(/Currently raised above Healthy/i)).toBeInTheDocument();
    });

    // One person is At Risk in the fixture -- the count appears, the name does not.
    expect(screen.queryByText("Priya")).toBeNull();
    expect(screen.queryByText("Ade")).toBeNull();
  });

  it("warns plainly when nothing has been validated", async () => {
    renderPage(<Home />);
    expect(
      await screen.findByText(/nothing it reports has been validated/i),
    ).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderPage(<Home />);
    await waitFor(() => screen.getByText(/People on record/i));
    expect((await axe(container)).violations).toEqual([]);
  });
});
