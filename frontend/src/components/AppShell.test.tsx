// Tests for the app shell.
//
// Same emphasis as the page tests: most of these check what the shell must NOT
// let a reader take away, or must not quietly lose. The shell is where the
// product's standing claims live -- the use constraint, the degraded notice,
// the fact that opening someone is a deliberate act -- so a regression here is
// a regression in what the tool says about itself.
//
// The sections are stubbed rather than imported. This file is about routing,
// nav state and banners; pulling the real pages in would make it slow and make
// a failure ambiguous between the shell and the section.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiKey } from "../api/client";
import type { ProviderStatus, RunProgress } from "../api/types";
import { AppShell } from "./AppShell";

// Typed against the generated response types, so a fixture cannot describe a
// response the API does not actually send.
const idle: RunProgress = {
  running: false,
  scope: null,
  done: 0,
  total: 0,
  current: "",
  error: null,
};

const healthy: ProviderStatus = {
  fallback_sequence: ["gemini-2.5-flash", "gemini-2.0-flash", "local-scorer"],
  last_successful_model: "gemini-2.5-flash",
  exhausted_models: [],
  local_only_mode: false,
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const routes: Record<string, unknown> = {
        "/run/progress": idle,
        "/models/status": healthy,
        ...overrides,
      };
      const key = Object.keys(routes).find((path) => url.includes(path));
      return { ok: true, status: 200, json: async () => (key ? routes[key] : {}) } as Response;
    }),
  );
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<div>OVERVIEW SECTION</div>} />
            <Route path="/cohort" element={<div>COHORT SECTION</div>} />
            <Route path="/person/:name" element={<div>PERSON SECTION</div>} />
            <Route path="/audit" element={<div>AUDIT SECTION</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  setApiKey("test-key");
  stubFetch();
});

afterEach(() => vi.unstubAllGlobals());

describe("navigation", () => {
  it("offers all eight sections", async () => {
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: /sections/i });
    const labels = within(nav)
      .getAllByRole("listitem")
      .map((li) => li.textContent);

    expect(labels).toEqual([
      "Overview",
      "Cohort",
      "Person detail",
      "Diagnostic room",
      "Ingest",
      "Simulator",
      "History",
      "Access trail",
    ]);
  });

  it("routes each address to its own section", async () => {
    renderAt("/cohort");
    expect(await screen.findByText("COHORT SECTION")).toBeInTheDocument();

    renderAt("/audit");
    expect(await screen.findByText("AUDIT SECTION")).toBeInTheDocument();
  });

  it("marks only the open section as current", async () => {
    renderAt("/cohort");
    const nav = screen.getByRole("navigation", { name: /sections/i });
    const current = within(nav).getAllByRole("link", { current: "page" });
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Cohort");
  });

  // Opening someone's assessment is written to the access trail, so it should
  // never be something you land on by clicking a nav item -- it is reached from
  // the cohort, by choosing a person.
  it("gives person detail no destination until someone is open", async () => {
    renderAt("/");
    const nav = screen.getByRole("navigation", { name: /sections/i });
    expect(within(nav).queryByRole("link", { name: "Person detail" })).toBeNull();
    expect(screen.getByText("Person detail")).toHaveAttribute("aria-disabled", "true");
  });

  it("makes person detail a real nav item once someone is open", async () => {
    renderAt("/person/Ade");
    const nav = screen.getByRole("navigation", { name: /sections/i });
    expect(within(nav).getByRole("link", { name: "Person detail" })).toBeInTheDocument();
  });
});

describe("standing banners", () => {
  // The wording is the product's stated position, not decoration. If someone
  // softens it, that should break a test.
  it("always states the use constraint", async () => {
    renderAt("/");
    const banner = screen.getByRole("complementary", { name: /use constraint/i });
    expect(banner).toHaveTextContent(/compares each person only to their own earlier weeks/i);
    expect(banner).toHaveTextContent(/does not rank people/i);
    expect(banner).toHaveTextContent(/does not recommend disciplinary action/i);
    expect(banner).toHaveTextContent(/written to the access trail/i);
  });

  it("says nothing about a degraded tier while the providers are healthy", async () => {
    renderAt("/");
    expect(screen.queryByText(/degraded tier/i)).toBeNull();
  });

  it("explains the degraded tier when the chain is unavailable", async () => {
    stubFetch({ "/models/status": { ...healthy, local_only_mode: true } });
    renderAt("/");

    expect(await screen.findByText(/degraded tier/i)).toBeInTheDocument();
    expect(screen.getByText(/local fallback scorer/i)).toBeInTheDocument();
    // The reason this notice exists: at this tier nobody gets a single number.
    expect(screen.getByText(/no single number is shown for anyone/i)).toBeInTheDocument();
  });

  it("reports real run progress rather than an animation", async () => {
    const running: RunProgress = {
      running: true,
      scope: "main",
      done: 3,
      total: 8,
      current: "Ade",
      error: null,
    };
    stubFetch({ "/run/progress": running });
    renderAt("/");

    expect(await screen.findByText("Evaluating Ade")).toBeInTheDocument();
    expect(screen.getByText("3 of 8")).toBeInTheDocument();
  });
});

describe("model block", () => {
  it("names the model that answered and the chain behind it", async () => {
    renderAt("/");
    // The active model appears twice by design: as the disclosure summary, and
    // again inside the chain marked "in use".
    expect(await screen.findAllByText("gemini-2.5-flash")).toHaveLength(2);
    expect(screen.getByText("in use")).toBeInTheDocument();

    // The whole chain is visible, not just the model currently answering --
    // that is the point of the disclosure.
    expect(screen.getByText("gemini-2.0-flash")).toBeInTheDocument();
    expect(screen.getByText("local-scorer")).toBeInTheDocument();
  });

  it("shows which models are exhausted and for how long", async () => {
    stubFetch({
      "/models/status": {
        ...healthy,
        last_successful_model: "gemini-2.0-flash",
        exhausted_models: [{ model: "gemini-2.5-flash", cooldown_remaining_seconds: 120 }],
      },
    });
    renderAt("/");

    expect(await screen.findByText(/exhausted · 2m/)).toBeInTheDocument();
  });

  // R1: the prototype's provider-call meter was removed deliberately. This
  // system has no hard limit, and a quota bar would draw a constraint that does
  // not exist. If one reappears, it should reappear as a decision.
  it("shows no call quota or usage limit", async () => {
    renderAt("/");
    expect(screen.queryByText(/provider calls/i)).toBeNull();
    expect(screen.queryByText(/quota/i)).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  // The prototype could be switched between populated, empty and degraded.
  // Those are API responses, not something an operator toggles.
  it("offers no demo-state switch", async () => {
    renderAt("/");
    expect(screen.queryByText(/demo state/i)).toBeNull();
    expect(screen.queryByText(/first run \(empty\)/i)).toBeNull();
  });
});

describe("accessibility", () => {
  it("has no detectable violations", async () => {
    const { container } = renderAt("/");
    await screen.findByRole("navigation", { name: /sections/i });
    expect((await axe(container)).violations).toEqual([]);
  });

  it("puts a skip link ahead of the navigation", async () => {
    renderAt("/");
    const skip = screen.getByRole("link", { name: /skip to content/i });
    expect(skip).toHaveAttribute("href", "#main-content");
    // It must come before the nav in the DOM or it saves nobody any tabbing.
    const nav = screen.getByRole("navigation", { name: /sections/i });
    expect(skip.compareDocumentPosition(nav) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
