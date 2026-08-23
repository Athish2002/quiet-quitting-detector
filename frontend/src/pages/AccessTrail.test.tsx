// frontend/src/pages/AccessTrail.test.tsx

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AccessTrail } from "./AccessTrail";

const mockAuditLogs = [
  {
    timestamp: "2026-08-23T08:00:00Z",
    accessor: "analyst_1",
    subject: "Ade",
    action: "VIEW_ASSESSMENT",
    status: "granted",
    hash: "a1b2c3d4e5f67890",
  },
  {
    timestamp: "2026-08-23T08:05:00Z",
    accessor: "manager_2",
    subject: "Priya",
    action: "VIEW_DIAGNOSTICS",
    status: "refused",
    hash: "f9e8d7c6b5a43210",
  },
];

function renderAccessTrail(mockData?: unknown, is404 = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      if (is404) {
        return {
          ok: false,
          status: 404,
          json: async () => ({ title: "Not found" }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => mockData ?? mockAuditLogs,
      } as Response;
    }),
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AccessTrail />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AccessTrail", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders section header and integrity notice", async () => {
    renderAccessTrail();

    expect(screen.getByText("ACCESS TRAIL")).toBeInTheDocument();
    expect(
      screen.getByText("Who looked at whose assessment."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Every row is cryptographically chained/i),
    ).toBeInTheDocument();
  });

  it("renders audit table rows with granted and refused statuses", async () => {
    renderAccessTrail();

    await waitFor(() => {
      expect(screen.getByText("analyst_1")).toBeInTheDocument();
    });

    expect(screen.getByText("Ade")).toBeInTheDocument();
    expect(screen.getByText("GRANTED")).toBeInTheDocument();

    expect(screen.getByText("manager_2")).toBeInTheDocument();
    expect(screen.getByText("Priya")).toBeInTheDocument();
    expect(screen.getByText("REFUSED")).toBeInTheDocument();
    expect(screen.getByText("a1b2c3d4")).toBeInTheDocument();
  });

  it("handles empty / 404 state gracefully", async () => {
    renderAccessTrail([], true);

    await waitFor(() => {
      expect(
        screen.getByText(/No access records yet/i),
      ).toBeInTheDocument();
    });
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderAccessTrail();
    await waitFor(() => screen.getByText("analyst_1"));
    expect((await axe(container)).violations).toEqual([]);
  });
});
